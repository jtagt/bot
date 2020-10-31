from pyomo.environ import *
from pyomo.opt import *

from config import SCIP_TIMELIMIT
from constants import RARITIES


def format_counts(counts):
    result = {}
    for (equipment_type, rarity, reforge), count in counts.get_values().items():
        count = round(count)
        if count > 0:
            if equipment_type not in result:
                result[equipment_type] = {}
            if rarity not in result[equipment_type]:
                result[equipment_type][rarity] = {}

            result[equipment_type][rarity][reforge] = count

    return result


def solve(m):
    s = SolverFactory('scip', executable='scip')
    s.options['limits/time'] = SCIP_TIMELIMIT
    result = s.solve(m)
    if result.solver.status == SolverStatus.aborted and result.solver.termination_condition == TerminationCondition.maxTimeLimit:
        return False
    return True


# noinspection PyUnresolvedReferences
def create_model(counts, reforge_set, only_blacksmith_reforges):
    m = ConcreteModel()
    m.reforge_set = Set(
        initialize=[
            (i, j, k) for i, count in counts.items() for j in RARITIES for k, stats in
            reforge_set[armor_check(i)].items()
            if j in stats and count[j] > 0 and (only_blacksmith_reforges is False or stats['blacksmith'] is True)
        ], ordered=True
    )
    m.reforge_counts = Var(
        m.reforge_set, domain=NonNegativeIntegers, initialize=0)
    m.eqn = ConstraintList()
    return m


def create_constraint_rule(stat, m, counts, profile, reforges_set, include_dungeon):
    rule = quicksum((reforges_set['talisman'][k][j].get(stat, 0) * m.reforge_counts['talisman', j, k] for i, j, k in
                     m.reforge_set if i == 'talisman'), linear=False)
    for equip in counts:
        if equip != 'talisman':
            for child in profile.stats.childrens:
                if child.type == equip:
                    rule += child.multiplier * (child.get_dungeon_bonus(stat) if include_dungeon else 1) * quicksum(
                        (reforges_set[armor_check(equip)][k][j].get(stat, 0) * m.reforge_counts[equip, j, k] for
                         i, j, k in m.reforge_set if i == equip), linear=False)
    return rule


def armor_check(armor):
    return 'armor' if armor in ('helmet', 'chestplate', 'leggings', 'boots') else armor


# TODO: Add gap limit = 0.10%
# TODO: possibly a thread limit = 4?
# noinspection PyUnresolvedReferences,PyTypeChecker,PyCallingNonCallable
def damage_optimizer(profile, *, perfect_crit_chance, attack_speed_limit, only_blacksmith_reforges, include_dungeon,
                     reforges_set):
    # overhead due to rounding
    if attack_speed_limit == 100:
        attack_speed_limit = 100.5
    # remove gilded if there is no midas
    if not profile.weapon.internal_name == 'MIDAS_SWORD' and not only_blacksmith_reforges:
        for reforge in reforges_set['sword'].keys():
            if reforge == 'gilded':
                reforges_set['sword'].pop('gilded')
                break
    # remove warped if there is no aspect of the end
    if not profile.weapon.internal_name == 'ASPECT_OF_THE_END' and not only_blacksmith_reforges:
        for reforge in reforges_set['sword'].keys():
            if reforge == 'warped':
                reforges_set['sword'].pop('warped')
                break

    armor_types = [type for type, piece in profile.armor.items(
    ) if armor_check(type) == 'armor' and piece is not None]
    equipment_types = ['talisman', profile.weapon.type] + armor_types

    counts = {
        'talisman': profile.talisman_counts,
        profile.weapon.type: {rarity: int(profile.weapon.rarity == rarity) for rarity in RARITIES},
        'helmet': {rarity: int(profile.armor['helmet'].rarity == rarity) for rarity in RARITIES} if profile.armor[
            'helmet'] else {rarity: 0 for rarity in RARITIES},
        'chestplate': {rarity: int(profile.armor['chestplate'].rarity == rarity) for rarity in RARITIES} if profile.armor[
            'chestplate'] else {rarity: 0 for rarity in RARITIES},
        'leggings': {rarity: int(profile.armor['leggings'].rarity == rarity) for rarity in RARITIES} if profile.armor[
            'leggings'] else {rarity: 0 for rarity in RARITIES},
        'boots': {rarity: int(profile.armor['boots'].rarity == rarity) for rarity in RARITIES} if profile.armor[
            'boots'] else {rarity: 0 for rarity in RARITIES},
    }

    m = create_model(counts, reforges_set, only_blacksmith_reforges)

    for equipment_type in equipment_types:
        reforges = reforges_set[armor_check(equipment_type)]
        sums = {rarity: [] for rarity in RARITIES}
        for reforge in reforges.keys():
            for rarity in reforges[reforge].keys():
                if rarity != 'blacksmith' and (
                        only_blacksmith_reforges is False or reforges[reforge]['blacksmith'] is True):
                    if counts[equipment_type][rarity] > 0:
                        sums[rarity].append(
                            m.reforge_counts[equipment_type, rarity, reforge])
        for rarity in RARITIES:
            if counts[equipment_type][rarity] > 0:
                m.eqn.add(quicksum(sums[rarity], linear=False)
                          == counts[equipment_type][rarity])

    # for stat in ['strength', 'crit damage'] + ['crit chance'] * perfect_crit_chance + ['attack speed'] * include_attack_speed:
    #     profile.stats.modifiers[stat].insert(0,
    #                                         lambda stat: stat + quicksum(
    #                                             damage_reforges[armor_check(i)][k][j].get(stat, 0) * m.reforge_counts[
    #                                                 i, j, k] for i, j, k in m.reforge_set))

    # --- variables ---
    m.s = Var(domain=Reals, initialize=400)
    m.cd = Var(domain=Reals, initialize=400)
    m.damage = Var(domain=Reals, initialize=10000)
    m.floored_strength = Var(domain=Integers, initialize=60)
    m.cc = Var(domain=Reals, initialize=100)
    if profile.weapon != 'LIVID_DAGGER':
        m.a = Var(domain=Reals, initialize=50)
    if only_blacksmith_reforges:
        m.m = profile.stats.multiplier
    else:
        m.m = Var(domain=Reals, initialize=1)
    if profile.weapon == 'MIDAS_SWORD' and not only_blacksmith_reforges:
        m.wd = Var(domain=Reals, initialize=200)
    else:
        m.wd = profile.weapon.stats.get_stat('damage', dungeon=include_dungeon)
    # ---

    # --- modifiers ---
    # manually add it here now, will find a better way to do it
    cd_tara_helm = m.s / \
        10 if profile.armor['helmet'] == 'TARANTULA_HELMET' else 0
    # ---

    # --- weapon damage ---
    if profile.weapon == 'MIDAS_SWORD' and not only_blacksmith_reforges:
        m.eqn.add(m.wd == profile.weapon.stats.get_stat('damage', base=True, dungeon=include_dungeon) + quicksum(
            (reforges_set['sword'][k][j].get('damage', 0) * m.reforge_counts['sword', j, k] for i, j, k in
             m.reforge_set if i == 'sword'), linear=False))
    # ---

    # --- multiplier ---
    if not only_blacksmith_reforges:
        m.eqn.add(m.m == profile.stats.multiplier + (quicksum(
            (m.reforge_counts[i, j, k] * 0.01 for i, j,
             k in m.reforge_set if i in armor_types and k == 'renowned'),
            linear=False) if not only_blacksmith_reforges else 0))
    # ---

    # --- crit chance ---
    cc_rule = create_constraint_rule(
        'crit chance', m, counts, profile, reforges_set, include_dungeon)
    m.eqn.add(
        m.cc == m.m * (cc_rule + profile.stats.get_stat('crit chance', base=True, raw=True, dungeon=include_dungeon)))
    if perfect_crit_chance:
        m.eqn.add(99.5 <= m.cc)
    # ---

    # --- attack speed ---
    if profile.weapon != 'LIVID_DAGGER':
        a_rule = create_constraint_rule(
            'attack speed', m, counts, profile, reforges_set, include_dungeon)
        m.eqn.add(
            m.a == m.m * (a_rule + profile.stats.get_stat('attack speed', base=True, raw=True, dungeon=include_dungeon)))
        if attack_speed_limit:
            m.eqn.add(m.a <= attack_speed_limit)
    # ---

    # --- strength ---
    strength_rule = create_constraint_rule(
        'strength', m, counts, profile, reforges_set, include_dungeon)
    m.eqn.add(
        m.s == m.m * (strength_rule + profile.stats.get_stat('strength', base=True, raw=True, dungeon=include_dungeon)))
    # ---

    # --- crit damage ---
    cd_rule = create_constraint_rule(
        'crit damage', m, counts, profile, reforges_set, include_dungeon)
    m.eqn.add(m.cd == m.m * (cd_rule + profile.stats.get_stat('crit damage', base=True, raw=True,
                                                              dungeon=include_dungeon) + cd_tara_helm))
    # ---

    m.eqn.add(m.floored_strength >= m.s / 5 - 0.9999)
    m.eqn.add(m.floored_strength <= m.s / 5)
    m.eqn.add(m.damage == (5 + m.wd + m.floored_strength)
              * (1 + m.s / 100) * (1 + m.cd / 100))

    if profile.weapon != 'LIVID_DAGGER':
        m.objective = Objective(expr=m.damage * (((m.a + 100) / 100) / 0.5) if attack_speed_limit else m.damage,
                                sense=maximize)
    else:
        m.objective = Objective(expr=m.damage * (((100 + 100) / 100) / 0.5) if attack_speed_limit else m.damage,
                                sense=maximize)
    is_optimized = solve(m)

    # debug stuff
    # from pyomo.util.infeasible import log_infeasible_constraints
    # log_infeasible_constraints(m, log_expression=True, log_variables=True)

    result_atk_speed = 100
    if profile.weapon != 'LIVID_DAGGER':
        result_atk_speed = m.a()
    result = {'strength': m.s(),
              'crit damage': m.cd(),
              'crit chance': m.cc(),
              'attack speed': result_atk_speed,
              'is optimized': is_optimized}

    if profile.weapon == 'MIDAS_SWORD' and not only_blacksmith_reforges:
        result.update({'damage': m.wd()})
    else:
        result.update({'damage': m.wd})

    return result, format_counts(m.reforge_counts)

# def ehp_optimizer(player, talisman_rarity_counts, *, only_blacksmith_reforges):
# equipment_types = ['talisman', 'armor']
# m = create_model(equipment_types, ehp_reforges)
#
# m.m = 1 + player.stats['multiplier'] / 100
#
# m.hp = Var(domain=Reals, initialize=1400)
# m.eqn.add(m.hp == max(0, m.m * (quicksum(ehp_reforges[i][k][j].get('health', 0) * m.reforge_counts[i, j, k] for i, j, k in m.reforge_set) + player.stats['health'])))
# m.d = Var(domain=Reals, initialize=700)
# m.eqn.add(m.d == max(0, m.m * (quicksum(ehp_reforges[i][k][j].get('defense', 0) * m.reforge_counts[i, j, k] for i, j, k in m.reforge_set) + player.stats['defense'])))
#
# counts = {'talisman': talisman_rarity_counts, 'armor': armor_rarity_counts}
# for equipment_type in equipment_types:
#     reforges = ehp_reforges[equipment_type]
#     sums = {rarity: [] for rarity in rarities}
#     for reforge in reforges.keys():
#         for rarity in reforges[reforge].keys():
#             sums[rarity].append(m.reforge_counts[equipment_type, rarity, reforge])
#     for rarity in rarities:
#         m.eqn.add(quicksum(sums[rarity]) == counts[equipment_type][rarity])
# m.objective = Objective(expr=(m.hp * (1 + m.d / 100)), sense=maximize)
# solve(m)
#
# return {'ehp': m.objective(), 'health': m.hp(), 'defense': m.d()}, format_counts(m.reforge_counts)


# def mastiff_ehp_optimizer(only_blacksmith_reforges):
#     if only_blacksmith_reforges:
#         return '''Reforge all your armor to fierce
# Reforge all your talismans to hurtful
# Reforge your sword/fishing rod to spicy
# Reforge your bow to rapid'''
#     else:
#         return '''Reforge all your armor to fierce
# Reforge all your talismans to hurtful
# Reforge your sword/fishing rod to spicy or fabled
# Reforge your bow to rapid'''
#
#
# def intelligence_optimizer(only_blacksmith_reforges):
#     if only_blacksmith_reforges:
#         return '''Reforge all your armor to wise
# Reforge all your common talismans to demonic
# Reforge all your other talismans to bizarre
# Reforge your sword/fishing rod to heroic
# Reforge your bow to deadly'''
#     else:
#         return '''Reforge all your armor to necrotic
# Reforge all your common talismans to demonic
# Reforge all your other talismans to bizarre
# Reforge your sword/fishing rod to heroic
# Reforge your bow to deadly'''
#
#
# def speed_optimizer(only_blacksmith_reforges):
#     if only_blacksmith_reforges:
#         return '''Reforge your common talismans to simple
# Reforge your other talismans to vivid
# Reforge your common and uncommon armor to mythic
# Reforge your other armor to light
# Sword/bow/fishing rod reforges don't matter'''
#     else:
#         return '''Reforge your common talismans to simple
# Reforge your other talismans to vivid
# Reforge your common and uncommon armor to renowned or spiked
# Reforge your other armor to light
# Sword/bow/fishing rod reforges don't matter'''

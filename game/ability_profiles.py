"""Expose legacy name-based defaults as editable data before names change."""
import copy


def editable_data(entry, data=None):
    result=copy.deepcopy(entry.data if data is None else data)
    if entry.kind!='ability':return result
    from .weaponry import wide_swing_profile,unarmed_profile
    from .stances import sphere_profile
    from .defenses import profile as defense_profile
    from .attack_sequences import profile as sequence_profile, standard_count
    profiles={'wide_swing':wide_swing_profile,'unarmed_combat':unarmed_profile,
              'elemental_sphere':sphere_profile,'damage_reduction':defense_profile,'attack_sequence':sequence_profile,
              'standard_attack_count':standard_count}
    for key,resolve in profiles.items():
        if key in result:continue
        if key in entry.data:result[key]=copy.deepcopy(entry.data[key])
        elif (value:=resolve(entry)) is not None:result[key]=copy.deepcopy(value)
    if 'miss_damage_divisor' not in result and 'miss_damage_divisor' in entry.data:
        result['miss_damage_divisor']=entry.data['miss_damage_divisor']
    return result

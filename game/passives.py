"""Conditional damage contributions with explicit scene-turn identity."""
from .statuses import status_name


def turn_token(scene):
    return f'{scene.pk}:{scene.state["round"]}:{scene.state["turn"]}' if scene else None


def boulder_bonus(character, ability, calc, scene):
    passive=next((a for a in character.abilities.all() if a.name=='Глыба'),None)
    if not passive or ability.data.get('category','active')!='active':return []
    data=ability.data
    result=[]
    token=turn_token(scene)
    available=not token or character.runtime.get('once_per_turn',{}).get('boulder')!=token
    from .weaponry import keywords
    melee=any(k.startswith('Ближний') for k in keywords(ability,calc))
    if melee and data.get('damage') and available:
        result.append({'key':'boulder','value':calc['mods'].get(passive.data.get('stat','wis'),0),
                       'type':'Земля','name':'Глыба','once_per_turn':True})
    # Only unconditional, already-compiled stun clauses qualify for this preview.
    # Other effect choices are resolved by the application workflow.
    stun=sum(abs(e.get('value',0)) for e in data.get('effects',[]) if not e.get('manual') and status_name(e)=='Оглушение')
    if stun:
        result.append({'key':'boulder_stun','value':stun,'type':'Земля','name':'Глыба · Оглушение','once_per_turn':False})
    return result

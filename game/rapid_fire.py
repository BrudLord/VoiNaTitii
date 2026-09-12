"""One preparation doubles attacks of the next ability, not actions or uses."""
NAME = 'Скорострельность'


def prepares(ability):
    value = ability.data.get('rapid_fire', True if ability.name == NAME else None)
    if value is not None and type(value) is not bool:
        raise ValueError('Скорострельность должна быть отметкой')
    return value


def multiplier(character, ability):
    return 2 if character.runtime.get('rapid_fire') and not prepares(ability) else 1


def consume(change, character, ability):
    """Call once per complete ability, never per individual attack."""
    previous = character.runtime.pop('rapid_fire', None)
    if previous:
        change.inputs['rapid_fire'] = {'consumed': True, 'source': previous['ability']}
    if prepares(ability):
        character.runtime['rapid_fire'] = {'ability': ability.pk}
        change.inputs['rapid_fire'] = {**change.inputs.get('rapid_fire', {}), 'prepared': True}

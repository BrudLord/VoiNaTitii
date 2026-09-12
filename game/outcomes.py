"""One attack resource, with a separately declared result for each target."""
VALUES={'hit','miss','critical'}


def for_target(payload,pk):
    return payload.get('target_outcomes',{}).get(str(pk or 0),payload.get('outcome','hit'))


def normalize(payload,ids,data,allowed=True):
    default=payload.get('outcome','hit')
    if default not in VALUES:raise ValueError('Выберите попадание, промах или крит')
    if 'target_outcomes' not in payload:
        if data.get('automatic_hit') and default=='miss':raise ValueError('Это умение попадает автоматически: промах невозможен')
        return payload
    rows=payload['target_outcomes']
    if not allowed or not (data.get('damage') or data.get('weapon')):
        raise ValueError('Отдельные исходы доступны для атаки')
    if not isinstance(rows,dict) or set(rows)!={str(pk) for pk in (ids or [0])} or any(not isinstance(value,str) or value not in VALUES for value in rows.values()):
        raise ValueError('Укажите исход для каждой выбранной цели')
    if data.get('automatic_hit') and 'miss' in rows.values():raise ValueError('Автоматическое попадание не может промахнуться')
    aggregate='miss' if all(value=='miss' for value in rows.values()) else 'critical' if all(value=='critical' for value in rows.values()) else 'hit'
    return {**payload,'outcome':aggregate,'target_outcomes':dict(rows)}

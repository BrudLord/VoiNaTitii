"""A content version lets live updates reuse the public reference book."""
import hashlib
import json
from .models import Entry
from . import crafting, enchantments
from .alignment import schema
from .statuses import STATUS, NEUTRAL, CONSTRUCTIVE


def payload():
    entries=list(Entry.objects.filter(archived=False).order_by('id'))
    fields=['id','kind','name','description','data','source']
    result={'catalog':[{key:getattr(e,key) for key in fields} for e in entries],
            'rules':{'crafting':crafting.catalogue(entries),'enchantments':enchantments.catalogue(entries),
                     'alignment':schema(),'statuses':list(STATUS),'neutral':NEUTRAL,'constructive':CONSTRUCTIVE}}
    encoded=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    result['catalog_revision']=hashlib.sha256(encoded).hexdigest()
    return result

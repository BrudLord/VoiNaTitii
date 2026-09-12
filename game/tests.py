import json
import uuid
from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Character, Campaign, Squad, Membership, Entry, Item, Session, Scene, Event, Clock
from .rules import fresh, computed, formula


class GameTests(TestCase):
    def setUp(self):
        self.gm = User.objects.create_superuser('admin', password='test-admin-password')
        self.alice = User.objects.create_user('alice', password='testing123')
        self.bob = User.objects.create_user('bob', password='testing123')
        self.school = Entry.objects.create(kind='school', name='Свет', data={'stat': 'cha'})
        self.a = Character.objects.create(owner=self.alice, name='А', stats={'cha': 16}, info={'school_id': self.school.id}, runtime=fresh(), private_notes='secret-A')
        self.b = Character.objects.create(owner=self.bob, name='Б', stats={}, runtime=fresh(), private_notes='secret-B')
        for c in [self.a, self.b]:
            c.runtime['hp'] = 10
            c.save()
        self.campaign = Campaign.objects.create(name='Кампания', notes='abc def xyz')
        self.squad = Squad.objects.create(campaign=self.campaign, name='Отряд')
        for c in [self.a, self.b]:
            Membership.objects.create(character=c, campaign=self.campaign, squad=self.squad)
        self.session = Session.objects.create(campaign=self.campaign, squad=self.squad, name='Встреча')
        self.session.characters.set([self.a, self.b])
        self.bless = Entry.objects.create(kind='ability', name='Благословение', data={'circle': 1, 'target': 'single', 'effects': [
            {'key': 'bless', 'stat': 'hit', 'value': 2, 'turns': 3}, {'stat': 'temp', 'value': 5},
            {'key': 'bless-dmg', 'stat': 'damage', 'value': 1, 'duration': 'battle'}]})
        self.a.abilities.add(self.bless)
        Clock.objects.create(pk=1)

    def post(self, user, data, expected=200, key=None):
        self.client.force_login(user)
        r = self.client.post('/api/action/', json.dumps({**data, 'key': key or str(uuid.uuid4())}), content_type='application/json')
        self.assertEqual(r.status_code, expected, r.content[:1000])
        return r.json()

    def start(self):
        result = self.post(self.gm, {'op': 'scene.start', 'session': self.session.id, 'initiative': {str(self.a.id): 20, str(self.b.id): 10}})
        return Scene.objects.get(pk=result['id'])

    def turn(self, scene, user):
        scene.refresh_from_db()
        self.post(user, {'op': 'scene.turn', 'scene': scene.id, 'version': scene.state})

    def test_authorization_and_private_notes(self):
        self.post(self.alice, {'op': 'hp', 'character': self.a.id, 'value': 40}, 403)
        self.post(self.alice, {'op': 'character.save', 'id': self.b.id}, 403)
        self.post(self.alice, {'op': 'entry.save', 'kind': 'ability', 'name': 'Cheat'}, 403)
        for user in [self.alice, self.gm]:
            self.client.force_login(user)
            data = self.client.get('/api/state/').json()
            b = next(c for c in data['characters'] if c['id'] == self.b.id)
            self.assertIsNone(b['private_notes'])
            self.assertNotIn('secret-B', json.dumps(data))
        outsider = User.objects.create_user('outsider')
        self.post(outsider, {'op': 'notes.shared', 'campaign': self.campaign.id, 'text': 'bad'}, 403)

    def test_free_character_edit_and_modifiers(self):
        self.post(self.alice, {'op': 'character.save', 'id': self.a.id, 'revision': 0, 'name': 'A', 'level': 7,
                             'stats': {'str': 9, 'dex': 13}, 'info': {}, 'abilities': [self.bless.id]})
        self.a.refresh_from_db()
        self.assertEqual(computed(self.a)['mods']['str'], -1)
        self.assertEqual(computed(self.a)['mods']['dex'], 1)
        self.assertEqual(self.a.stats['con'], 10)
        self.assertEqual(self.a.runtime['hp'], 10)
        self.post(self.alice, {'op': 'character.save', 'id': self.a.id, 'revision': 0}, 400)

    def test_blessing_three_target_turns_and_end(self):
        scene = self.start()
        self.post(self.alice, {'op': 'ability.use', 'character': self.a.id, 'ability': self.bless.id, 'targets': [self.b.id]})
        self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['temp'], 5)
        self.assertEqual(computed(self.b)['hit'], 2)
        for i in range(3):
            self.turn(scene, self.alice)
            self.b.refresh_from_db()
            self.assertEqual(computed(self.b)['hit'], 2)
            self.turn(scene, self.bob)
        self.b.refresh_from_db()
        self.assertEqual(computed(self.b)['hit'], 0)
        self.assertEqual(computed(self.b)['damage'], 1)
        scene.refresh_from_db()
        self.post(self.gm, {'op': 'scene.end', 'scene': scene.id, 'version': scene.state})
        self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['hp'], computed(self.b)['max_hp'])
        self.assertEqual(self.b.runtime['temp'], 0)
        self.post(self.gm, {'op': 'undo'})
        self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['temp'], 5)
        self.assertEqual(self.b.runtime['hp'], 10)

    def test_no_double_application_and_undo_redo(self):
        self.start()
        key = str(uuid.uuid4())
        data = {'op': 'ability.use', 'character': self.a.id, 'ability': self.bless.id, 'targets': [self.b.id]}
        self.post(self.alice, data, key=key)
        self.post(self.alice, data, key=key)
        self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['used'][str(self.bless.id)], 1)
        self.post(self.alice, {'op': 'undo'})
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'], 1)
        self.assertEqual(self.b.runtime['temp'], 0)
        self.post(self.alice, {'op': 'redo'})
        self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['temp'], 5)

    def test_hp_bounds_temp_pool_and_dependencies(self):
        self.start()
        self.post(self.alice, {'op': 'ability.use', 'character': self.a.id, 'ability': self.bless.id, 'targets': [self.b.id]})
        self.post(self.gm, {'op': 'hp', 'character': self.b.id, 'mode': 'temp', 'value': 3})
        self.b.refresh_from_db(); self.assertEqual(self.b.runtime['temp'], 5)
        self.post(self.gm, {'op': 'hp', 'character': self.b.id, 'mode': 'damage', 'value': 7})
        self.b.refresh_from_db(); self.assertEqual(self.b.runtime['hp'], 8)
        self.assertEqual(self.b.runtime['temp'], 0)
        self.post(self.alice, {'op': 'undo'}, 400)
        self.post(self.gm, {'op': 'hp', 'character': self.b.id, 'mode': 'heal', 'value': 10000})
        self.b.refresh_from_db(); self.assertEqual(self.b.runtime['hp'], computed(self.b)['max_hp'])
        self.post(self.gm, {'op': 'hp', 'character': self.b.id, 'mode': 'damage', 'value': 10000})
        self.b.refresh_from_db(); self.assertEqual(self.b.runtime['hp'], 0)

    def test_dice_wait_and_preserved_input(self):
        self.start()
        ray = Entry.objects.create(kind='ability', name='Луч', data={'formula': '1к6 + Мод', 'damage': True})
        self.a.abilities.add(ray)
        data = {'op': 'ability.use', 'character': self.a.id, 'ability': ray.id, 'targets': []}
        self.post(self.alice, data, 400)
        self.a.refresh_from_db(); self.assertEqual(self.a.runtime['actions']['main'], 1)
        self.post(self.alice, {**data, 'roll_result': 'к6 = 4'})
        self.assertEqual(Event.objects.last().inputs['roll_result'], 'к6 = 4')
        self.post(self.alice, {'op': 'undo'}); self.post(self.alice, {'op': 'redo'})
        self.assertEqual(Event.objects.last().inputs['roll_result'], 'к6 = 4')

    def test_shared_notes_merge_and_conflict(self):
        self.post(self.alice, {'op': 'notes.shared', 'campaign': self.campaign.id, 'base': 'abc def xyz', 'text': 'ABC def xyz'})
        self.post(self.bob, {'op': 'notes.shared', 'campaign': self.campaign.id, 'base': 'abc def xyz', 'text': 'abc def XYZ'})
        self.campaign.refresh_from_db(); self.assertEqual(self.campaign.notes, 'ABC def XYZ')
        self.post(self.alice, {'op': 'notes.shared', 'campaign': self.campaign.id, 'base': 'abc def xyz', 'text': 'Other def xyz'}, 400)

    def test_item_transfer_no_copy_and_campaign_access(self):
        item = Item.objects.create(campaign=self.campaign, name='Зелье', quantity=1)
        self.post(self.alice, {'op': 'item.transfer', 'id': item.id, 'character': self.a.id})
        self.post(self.bob, {'op': 'item.transfer', 'id': item.id, 'character': self.b.id}, 403)
        self.assertEqual(Item.objects.count(), 1)
        self.post(self.alice, {'op': 'membership', 'character': self.b.id, 'campaign': self.campaign.id}, 403)

    def test_aura_selection_and_source_removal(self):
        self.start()
        aura = Entry.objects.create(kind='ability', name='Аура', data={'category': 'passive', 'aura': True,
                   'effects': [{'stat': 'ac', 'value': 1}]})
        self.a.abilities.add(aura)
        self.post(self.alice, {'op': 'aura.set', 'character': self.a.id, 'ability': aura.id, 'targets': [self.b.id]})
        self.b.refresh_from_db(); self.assertEqual(computed(self.b)['ac'], 6)
        self.post(self.alice, {'op': 'aura.set', 'character': self.a.id, 'ability': aura.id, 'targets': []})
        self.b.refresh_from_db(); self.assertEqual(computed(self.b)['ac'], 5)

    def test_critical_examples(self):
        dagger = Item.objects.create(character=self.a, name='Кинжал', equipped=True, data={'dice': '1к4', 'stat': 'dex'})
        attack = Entry.objects.create(kind='ability', name='Атака', data={'formula': '1Ор', 'weapon': True})
        self.assertEqual(formula(self.a, attack, True), '2к4')
        dagger.data['crit'] = 1; dagger.save()
        self.assertEqual(formula(self.a, attack, True), '3к4')
        attack.data['formula'] = '2Ор'
        self.assertEqual(formula(self.a, attack, True), '6к4')
        orc = Entry.objects.create(kind='race', name='Орк', data={'orc': True})
        self.a.info['race_id'] = orc.id
        self.assertEqual(formula(self.a, attack, True), '6к4 + 1к4')

    def test_csrf_and_registration(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        self.assertEqual(client.post('/api/action/', '{}', content_type='application/json').status_code, 403)
        response = self.client.post('/register/', {'username': 'newplayer', 'password1': 'safe-password-123', 'password2': 'safe-password-123'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.get(username='newplayer').is_staff)

    def test_join_campaign_without_character(self):
        newcomer = User.objects.create_user('newcomer', password='testing123')
        self.post(newcomer, {'op': 'notes.shared', 'campaign': self.campaign.id, 'base': self.campaign.notes, 'text': 'hello'}, 403)
        self.post(newcomer, {'op': 'campaign.join', 'campaign': self.campaign.id})
        self.post(newcomer, {'op': 'campaign.join', 'campaign': self.campaign.id})
        self.assertEqual(self.campaign.players.filter(pk=newcomer.pk).count(), 1)
        self.assertFalse(Character.objects.filter(owner=newcomer).exists())
        state = self.client.get('/api/state/').json()
        campaign = next(c for c in state['campaigns'] if c['id'] == self.campaign.id)
        self.assertTrue(campaign['member'])
        self.assertEqual(campaign['notes'], self.campaign.notes)
        self.assertIn({'id': newcomer.id, 'username': newcomer.username}, campaign['players'])
        self.post(newcomer, {'op': 'notes.shared', 'campaign': self.campaign.id, 'base': self.campaign.notes, 'text': 'hello'})
        result = self.post(newcomer, {'op': 'character.save', 'name': 'Поздний герой', 'campaign': self.campaign.id})
        character = Character.objects.get(pk=result['id'])
        self.assertEqual(character.owner, newcomer)
        self.assertTrue(character.memberships.filter(campaign=self.campaign, squad=None).exists())
        self.post(newcomer, {'op': 'membership', 'character': character.id, 'campaign': self.campaign.id, 'leave': True})
        self.assertTrue(self.campaign.players.filter(pk=newcomer.pk).exists())
        self.post(newcomer, {'op': 'hp', 'character': self.a.id, 'mode': 'heal', 'value': 1}, 403)

    def test_book_choices_and_character_dependencies(self):
        from django.conf import settings
        from .book_choices import book_choices
        choices = book_choices((settings.BASE_DIR / 'rules/player-book.txt').read_text())
        self.assertEqual(sum(kind == 'class' for kind, _ in choices), 41)
        self.assertEqual(sum(kind == 'race' for kind, _ in choices), 10)
        self.assertEqual(choices['class', 'Мистический лучник']['allowed_schools'], ['Луки', 'Холод', 'Воздух'])
        self.assertEqual(len(choices['class', 'Элементалист']['allowed_schools']), 10)
        self.assertIn('Орки гор', choices['race', 'Орк']['subraces'])
        race = Entry.objects.create(kind='race', name='Орк', data=choices['race', 'Орк'])
        klass = Entry.objects.create(kind='class', name='Паладин Света', data=choices['class', 'Паладин Света'])
        shield = Entry.objects.create(kind='school', name='Щиты')
        fire = Entry.objects.create(kind='school', name='Огонь')
        data = {'op': 'character.save', 'name': 'Паладин', 'info': {'race_id': race.id, 'subrace': 'Орки гор',
                'class_id': klass.id, 'school_id': self.school.id, 'secondary_school_id': shield.id}}
        result = self.post(self.alice, data)
        self.assertEqual(Character.objects.get(pk=result['id']).info['subrace'], 'Орки гор')
        self.post(self.alice, {**data, 'info': {**data['info'], 'subrace': 'Вампиры'}}, 400)
        self.post(self.alice, {**data, 'info': {**data['info'], 'school_id': fire.id}}, 400)
        self.post(self.alice, {**data, 'info': {**data['info'], 'secondary_school_id': self.school.id}}, 400)
        # A legacy sheet with a school but no class can still save unrelated edits.
        self.post(self.alice, {'op': 'character.save', 'id': self.a.id, 'revision': self.a.revision,
                             'name': 'Старый лист', 'info': self.a.info})

    def test_audit_racial_and_passive_hp_and_skill_calculation(self):
        race = Entry.objects.create(kind='race', name='Гном', data={'hp_bonus': 5, 'speed': 5})
        klass = Entry.objects.create(kind='class', name='Класс', data={'hp_base': 18, 'hp_level': 4, 'skill': 'История'})
        passive = Entry.objects.create(kind='ability', name='Укрепленные органы', data={'category': 'passive', 'passive_hp': 10})
        self.a.info.update(race_id=race.id, class_id=klass.id)
        self.a.abilities.add(passive)
        calc = computed(self.a)
        self.assertEqual(calc['max_hp'], 43)
        self.assertEqual(calc['speed'], 5)
        self.assertTrue(calc['skills']['История']['trained'])
        self.a.info['skill_overrides'] = {'История': False}
        self.assertFalse(computed(self.a)['skills']['История']['trained'])
        race.data={'ac_bonus':1};race.save()
        self.assertEqual(computed(self.a)['ac'], 6)

    def test_audit_weapon_proficiency_selection_and_item_effects(self):
        school=Entry.objects.create(kind='school',name='Кинжалы',data={'stat':'dex'})
        self.a.stats['dex']=16
        dagger=Item.objects.create(character=self.a,name='Кинжал',equipped=True,data={'dice':'1к4','stat':'dex','families':['Кинжалы']})
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'formula':'1Ор + Мод'})
        self.assertEqual(formula(self.a,attack),'1к4 + 0')
        self.a.info['school_id']=school.pk
        self.assertEqual(formula(self.a,attack),'1к4 + 3')
        self.a.runtime['weapon_id']=0
        self.assertEqual(formula(self.a,attack),'0')
        Item.objects.create(character=self.a,name='Амулет',equipped=True,data={'item_type':'other','armor':2,'effects':[{'stat':'max_hp','value':4}]})
        Item.objects.create(character=self.a,name='Латы',equipped=True,data={'item_type':'armor','armor':5})
        self.assertEqual(computed(self.a)['ac'],15)
        self.assertEqual(computed(self.a)['max_hp'],32)

    def test_audit_item_equip_undo_during_combat(self):
        item=Item.objects.create(character=self.a,name='Кинжал',data={'dice':'1к4','item_type':'weapon'})
        self.start()
        self.post(self.alice,{'op':'item.equip','id':item.id})
        item.refresh_from_db();self.a.refresh_from_db()
        self.assertTrue(item.equipped);self.assertEqual(self.a.runtime['actions']['main'],0)
        self.post(self.alice,{'op':'undo'})
        item.refresh_from_db();self.a.refresh_from_db()
        self.assertFalse(item.equipped);self.assertEqual(self.a.runtime['actions']['main'],1)
        self.post(self.alice,{'op':'redo'})
        item.refresh_from_db();self.assertTrue(item.equipped)
        self.post(self.alice,{'op':'item.delete','id':item.id},400)

    def test_audit_negative_status_strength_and_reaction(self):
        from .rules import put_effect
        from .statuses import apply_status
        put_effect(self.a,{'key':'curse','value':-2})
        put_effect(self.a,{'key':'curse','value':-5})
        self.assertEqual(self.a.runtime['effects'][0]['value'],-5)
        self.a.runtime['effects']=[]
        apply_status(self.a,{'name':'Проклятье','stat':'hit','value':-3,'remaining':3,'duration':'turns'})
        incoming={'name':'Благословение','stat':'hit','value':2,'remaining':3,'duration':'turns'}
        with self.assertRaises(ValueError):apply_status(self.a,incoming)
        apply_status(self.a,incoming,'status:Проклятье')
        self.assertEqual(self.a.runtime['effects'],[])
        apply_status(self.a,{'name':'Оглушение','stat':'status','value':2,'remaining':3,'duration':'turns'})
        apply_status(self.a,{'name':'Оглушение','stat':'status','value':2,'remaining':3,'duration':'turns'})
        self.assertEqual(self.a.runtime['effects'][0]['value'],4)

    def test_audit_reaction_wait_is_atomic(self):
        scene=self.start()
        self.post(self.gm,{'op':'effect.apply','character':self.b.id,'name':'Проклятье','value':3})
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':self.bless.id,'targets':[self.b.id]},400)
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['main'],1)
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':self.bless.id,'targets':[self.b.id],
                            'reactions':{f'{self.b.id}:0':'status:Проклятье'}})
        self.b.refresh_from_db();self.assertEqual(computed(self.b)['hit'],0)
        self.assertEqual(self.b.runtime['temp'],5)
        self.assertEqual(computed(self.b)['damage'],1)

    def test_audit_check_records_physical_roll_without_spending(self):
        result=self.post(self.alice,{'op':'check.roll','character':self.a.id,'skill':'История','roll':7,'specialization':'Военная история'})
        self.assertEqual(result['total'],10)
        event=Event.objects.last();self.assertEqual(event.inputs['total'],10)
        self.post(self.alice,{'op':'undo'});event.refresh_from_db();self.assertTrue(event.undone)
        self.post(self.bob,{'op':'check.roll','character':self.a.id,'skill':'История','roll':7},403)

    def test_audit_book_import_complete_sources_and_safe_fixed_effects(self):
        from django.conf import settings
        from .book_audit import records, abilities
        text=(settings.BASE_DIR/'rules/player-book.txt').read_text()
        rows=list(abilities(text));self.assertEqual(len(rows),863)
        self.assertEqual(sum(name=='Сквозной удар' for name,_,_,_ in rows),2)
        fixed=next(data for name,_,data,_ in rows if name=='Жизненный запас')
        self.assertIn({'stat':'temp','value':5},fixed['effects'])
        heal=next(data for name,_,data,_ in rows if name=='Исцеление')
        self.assertNotIn('effects',heal)
        self.assertTrue(heal['rolls'])
        specs=[name for kind,name,_,_ in records(text) if kind=='specialization']
        self.assertIn('Военная история',specs);self.assertIn('Хавнгрим',specs)

    def test_audit_elemental_damage_formula(self):
        from pathlib import Path
        from .book_audit import abilities
        rows={name:data for name,desc,data,source in abilities(Path('rules/player-book.txt').read_text())}
        self.assertEqual(rows['Волшебная стрела']['formula'],'1к6+Мод')
        self.assertTrue(rows['Волшебная стрела']['damage'])
        self.assertTrue(rows['Дух зверя']['aura'])
        self.assertEqual(rows['Дух зверя']['effects'][0]['value'],1)
        self.assertEqual(rows['Миазмы']['effects'][0]['value'],-1)
        self.assertTrue(rows['Аура жизни']['aura'])

    def test_audit_three_secondary_schools(self):
        klass=Entry.objects.create(kind='class',name='Стихийный маг',data={'extra_schools':3,'allowed_schools':['Огонь','Вода','Земля','Воздух']})
        schools=[Entry.objects.create(kind='school',name=n) for n in klass.data['allowed_schools']]
        result=self.post(self.alice,{'op':'character.save','name':'Маг','info':{'class_id':klass.id,'school_id':schools[0].id,
            'secondary_school_id':schools[1].id,'additional_school_ids':[schools[2].id,schools[3].id]}})
        self.assertEqual(len(Character.objects.get(pk=result['id']).info['additional_school_ids']),2)

    def test_journal_membership_and_concurrent_edits(self):
        from .models import JournalEntry
        payload={'op':'journal.save','campaign':self.campaign.id,'title':'Найти кузнеца','kind':'quest',
                 'body':'Северный город','person':'Петри','reward':'300 золотых','status':'active',
                 'steps':[{'text':'Узнать дорогу','done':False}],'tags':['Город','Город']}
        outsider=User.objects.create_user('traveller')
        self.post(outsider,payload,403)
        self.post(outsider,{'op':'campaign.join','campaign':self.campaign.id})
        created=self.post(outsider,payload)
        quest=JournalEntry.objects.get(pk=created['id'])
        self.assertEqual(quest.tags,['Город'])
        changed={**payload,'id':quest.id,'revision':1,'status':'done'}
        self.post(self.alice,changed)
        self.post(self.bob,{**changed,'body':'Старая версия'},400)
        quest.refresh_from_db();self.assertEqual(quest.status,'done');self.assertEqual(quest.body,'Северный город')
        self.post(self.bob,{'op':'journal.save','campaign':self.campaign.id,'id':quest.id,'revision':2,'archived':True})
        quest.refresh_from_db();self.assertTrue(quest.archived)
        self.post(self.bob,{'op':'journal.save','campaign':self.campaign.id,'id':quest.id,'revision':3,'archived':False})
        other=Campaign.objects.create(name='Другой мир');other.players.add(self.bob)
        self.post(self.bob,{**changed,'campaign':other.id,'revision':4},404)
        self.client.force_login(self.alice)
        data=self.client.get('/api/state/').json()
        shared=next(c for c in data['campaigns'] if c['id']==self.campaign.id)
        self.assertEqual(shared['journal'][0]['person'],'Петри')
        stranger=User.objects.create_user('stranger')
        self.client.force_login(stranger)
        shared=next(c for c in self.client.get('/api/state/').json()['campaigns'] if c['id']==self.campaign.id)
        self.assertEqual(shared['journal'],[])

    def test_journal_validation(self):
        self.post(self.alice,{'op':'journal.save','campaign':self.campaign.id,'title':'','steps':[]},400)
        self.post(self.alice,{'op':'journal.save','campaign':self.campaign.id,'title':'Задание','steps':[{'text':'Этап','done':'yes'}]},400)
        self.post(self.alice,{'op':'journal.save','campaign':self.campaign.id,'title':'Задание','status':'unknown'},400)

    def test_alignment_diagram_solid_and_dotted_paths(self):
        from .alignment import available_priorities, validate_alignment, PAIRS
        import itertools
        self.assertEqual(available_priorities(['Личное','Свобода','Хаос']),{'Независимость','Творчество'})
        self.assertEqual(available_priorities(['Личное','Необходимость','Хаос']),{'Эгоизм','Адаптация','Интуиция'})
        self.assertEqual(available_priorities(['Личное','Необходимость','Хаос'],'Порядок'),{'Статус','Закон','Интуиция'})
        self.assertEqual(available_priorities(['Общее','Свобода','Порядок']),{'Альтруизм','Решимость','Система'})
        for base in itertools.product(*PAIRS):
            for extra in ['',*[v for pair in PAIRS for v in pair if v not in base]]:
                options=validate_alignment({'alignment_values':list(base),'alignment_extra':extra})
                self.assertGreaterEqual(len(options),2)
        for info in [{'alignment_values':['Личное','Общее','Хаос']},
                     {'alignment_values':['Личное','Свобода','Хаос'],'alignment_extra':'Хаос'},
                     {'alignment_values':['Личное','','Хаос'],'alignment_extra':'Порядок'}]:
            with self.assertRaises(ValueError):validate_alignment(info)

    def test_alignment_priorities_validated_against_source(self):
        independent=Entry.objects.create(kind='effect',name='Независимость',data={'priority':True})
        creative=Entry.objects.create(kind='effect',name='Творчество',data={'priority':True})
        ego=Entry.objects.create(kind='effect',name='Эгоизм',data={'priority':True})
        p={'op':'character.save','id':self.a.id,'revision':0,'name':'А','level':1,
           'info':{'alignment_values':['Личное','Свобода','Хаос'],'priorities':[independent.id,creative.id]}}
        self.post(self.alice,p)
        self.a.refresh_from_db();self.assertEqual(self.a.info['priorities'],[independent.id,creative.id])
        p['revision']=self.a.revision;p['info']['priorities']=[ego.id,creative.id]
        self.post(self.alice,p,400)
        self.a.refresh_from_db();self.assertEqual(self.a.info['priorities'],[independent.id,creative.id])

    def test_typed_items_currency_and_equipment(self):
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Золото','quantity':0,'equipped':True,
                             'data':{'item_type':'currency','armor':50,'effects':[{'stat':'max_hp','value':100}]}})
        money=self.a.items.get(name='Золото')
        self.assertFalse(money.equipped);self.assertEqual(money.data,{'item_type':'currency'});self.assertEqual(money.quantity,0)
        self.post(self.alice,{'op':'item.equip','id':money.id},400)
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Зелье','quantity':2,'equipped':True,'data':{'item_type':'consumable','description':'Лечит после броска'}})
        potion=self.a.items.get(name='Зелье');self.assertFalse(potion.equipped)
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Сломанное оружие','quantity':1,'data':{'item_type':'weapon','dice':'eval(1)'}},400)
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Кольчуга','quantity':1,'equipped':True,
                             'data':{'item_type':'armor','armor':4,'effects':[{'key':'item_bonus:max_hp','stat':'max_hp','value':5}]}})
        self.assertEqual(computed(self.a)['ac'],9)
        self.assertEqual(computed(self.a)['max_hp'],33)

    def test_boulder_bonus_once_per_target_scene_turn_and_undo(self):
        boulder=Entry.objects.create(kind='ability',name='Глыба',data={'category':'passive','stat':'wis'})
        attack=Entry.objects.create(kind='ability',name='Ближний удар',data={'category':'active','action':'free',
                                   'formula':'1к6','damage':True,'rolls':True,'keywords':['Ближний']})
        self.a.abilities.add(boulder,attack);self.a.stats['wis']=16;self.a.save()
        scene=self.start()
        self.assertEqual(formula(self.a,attack,scene=scene),'1к6 +3 [Земля]')
        p={'op':'ability.use','character':self.a.id,'ability':attack.id,'roll_result':'12','outcome':'miss'}
        self.post(self.alice,p);self.a.refresh_from_db()
        self.assertEqual(formula(self.a,attack,scene=scene),'1к6 +3 [Земля]')
        self.post(self.alice,{**p,'outcome':'hit'});self.a.refresh_from_db()
        self.assertEqual(formula(self.a,attack,scene=scene),'1к6')
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(formula(self.a,attack,True,scene=scene),'2к6 +3 [Земля]')
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db()
        self.assertEqual(formula(self.a,attack,scene=scene),'1к6')
        self.turn(scene,self.alice);scene.refresh_from_db();self.a.refresh_from_db()
        self.assertEqual(formula(self.a,attack,scene=scene),'1к6 +3 [Земля]')
        attack.data['keywords']=['Дальнобойный 5'];attack.save()
        self.assertEqual(formula(self.a,attack,scene=scene),'1к6')

    def test_boulder_stun_flat_damage(self):
        boulder=Entry.objects.create(kind='ability',name='Глыба',data={'category':'passive','stat':'wis'})
        self.a.abilities.add(boulder)
        spell=Entry.objects.create(kind='ability',name='Разрыв друзы',data={'category':'active','formula':'1к6','damage':True,
                                  'keywords':['Вокруг 1'],'effects':[{'name':'Оглушение','stat':'status','value':3}]})
        self.assertEqual(formula(self.a,spell),'1к6 +3 [Земля]')

    def test_weapon_bonuses_follow_selected_weapon(self):
        first=Item.objects.create(character=self.a,name='Первый кинжал',equipped=True,data={'dice':'1к4','effects':[{'stat':'hit','value':1}]})
        second=Item.objects.create(character=self.a,name='Второй кинжал',equipped=True,data={'dice':'1к4','effects':[{'stat':'hit','value':4}]})
        self.a.runtime['weapon_id']=first.id
        self.assertEqual(computed(self.a)['hit'],1)
        self.a.runtime['weapon_id']=second.id
        self.assertEqual(computed(self.a)['hit'],4)
        self.a.runtime['weapon_id']=0
        self.assertEqual(computed(self.a)['hit'],0)

    def test_remove_effect_uses_effect_key_not_request_receipt(self):
        self.post(self.gm,{'op':'effect.apply','character':self.a.id,'name':'Благословение','value':2})
        self.post(self.gm,{'op':'effect.apply','character':self.a.id,'remove':True,'effect_key':'status:Благословение'})
        self.a.refresh_from_db();self.assertEqual(computed(self.a)['hit'],0)
        self.post(self.gm,{'op':'undo'})
        self.a.refresh_from_db();self.assertEqual(computed(self.a)['hit'],2)

import json
import uuid
from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Character, Campaign, Squad, Membership, Entry, Item, Session, Scene, Event, Clock
from .rules import fresh, computed, formula


class GameTests(TestCase):
    def test_archived_passives_stop_affecting_sheet_and_attacks(self):
        from .views import serialize_char
        vigor=Entry.objects.create(kind='ability',name='Живучесть',data={'category':'passive','passive_hp':10,
            'effects':[{'stat':'dex','value':2},{'stat':'ac','value':1}]})
        boulder=Entry.objects.create(kind='ability',name='Глыба',data={'category':'passive','stat':'cha'})
        accuracy=Entry.objects.create(kind='ability',name='Мистическая точность',data={'category':'passive'})
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'damage':True,'formula':'1Ор + Мод','keywords':['Ближний 1']})
        Item.objects.create(character=self.a,name='Клинок',equipped=True,data={'dice':'1к6','item_type':'weapon','no_proficiency':True})
        self.a.abilities.add(vigor,boulder,accuracy)
        initial=serialize_char(self.a,self.alice)
        self.assertEqual((initial['calc']['stats']['dex'],initial['calc']['ac'],initial['calc']['max_hp']),(12,7,38))
        row=next(a for a in initial['abilities'] if a['id']==attack.id)
        self.assertEqual(row['hit_bonus'],3)
        self.assertIn('+3 [Земля]',row['formula'])
        for passive in (vigor,boulder,accuracy):
            self.post(self.gm,{'op':'entry.save','id':passive.id,'archive':True})
        final=serialize_char(Character.objects.get(pk=self.a.pk),self.alice)
        self.assertEqual((final['calc']['stats']['dex'],final['calc']['ac'],final['calc']['max_hp']),(10,5,28))
        row=next(a for a in final['abilities'] if a['id']==attack.id)
        self.assertEqual(row['hit_bonus'],0)
        self.assertNotIn('[Земля]',row['formula'])
        self.assertFalse({vigor.id,boulder.id,accuracy.id}.intersection(a['id'] for a in final['abilities']))

    def test_intuitive_bow_proficiency_uses_bow_modifier_and_can_be_removed(self):
        from .views import serialize_char
        Entry.objects.create(kind='school',name='Луки',data={'stat':'dex'})
        passive=Entry.objects.create(kind='ability',name='Интуитивное владение',data={'category':'passive'})
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'damage':True,'formula':'1Ор + Мод'})
        Item.objects.create(character=self.a,name='Лук',equipped=True,data={'dice':'1к6','item_type':'weapon','families':['Луки'],'stat':'dex'})
        self.a.stats['dex']=14;self.a.save()
        self.assertFalse(computed(self.a)['weapon_proficient'])
        self.assertEqual(formula(self.a,attack),'1к6 + 0')
        self.a.abilities.add(passive)
        self.assertTrue(computed(self.a)['weapon_proficient'])
        self.assertEqual(formula(self.a,attack),'1к6 + 2')
        self.assertEqual(self.a.info['school_id'],self.school.pk)
        rendered=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==passive.id)
        self.assertFalse(rendered['data']['manual'])
        self.a.abilities.remove(passive)
        self.assertEqual(formula(self.a,attack),'1к6 + 0')
        self.a.abilities.add(passive);passive.archived=True;passive.save()
        self.assertFalse(computed(self.a)['weapon_proficient'])

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

    def charm(self,name):
        return Entry.objects.create(kind='ability',name=name,data={'category':'noncombat'})

    def test_enchantment_compatibility_and_empty_equipment(self):
        fire=self.charm('Малое зачарование огня')
        p={'op':'item.save','character':self.a.id,'name':'Меч','quantity':1,'equipped':True,
           'data':{'item_type':'weapon','dice':'1к6','enchantments':[fire.id]}}
        self.post(self.alice,p)
        attack=Entry.objects.create(kind='ability',name='Удар',data={'weapon':True,'formula':'1Ор','damage':True})
        self.assertEqual(formula(self.a,attack),'1к6 +1')
        self.assertEqual(formula(self.a,attack,True),'2к6 +1')
        self.post(self.alice,{**p,'data':{'item_type':'armor','enchantments':[fire.id]}},400)
        self.post(self.alice,{**p,'data':{'item_type':'weapon','enchantments':[fire.id,fire.id]}},400)
        item=self.a.items.get(name='Меч')
        self.post(self.alice,{**p,'id':item.id,'quantity':0})
        item.refresh_from_db();self.assertFalse(item.equipped)
        self.post(self.alice,{'op':'item.equip','id':item.id},400)

    def test_enchantments_focus_weapon_scope_and_selection(self):
        light=self.charm('Малое зачарование света');lightning=self.charm('Малое зачарование молнии')
        sword=Item.objects.create(character=self.a,name='Меч',equipped=True,data={'item_type':'weapon','dice':'1к6','enchantments':[light.id]})
        focus=Item.objects.create(character=self.a,name='Кольцо',equipped=True,data={'item_type':'focus','enchantments':[lightning.id,light.id]})
        attack=Entry.objects.create(kind='ability',name='Удар',data={'weapon':True,'formula':'1Ор','damage':True})
        magic=Entry.objects.create(kind='ability',name='Молния',data={'school_name':'Молния','formula':'1к8','damage':True})
        plain=Entry.objects.create(kind='ability',name='Камень',data={'formula':'1к4','damage':True})
        self.a.abilities.add(attack,magic,plain)
        from .views import serialize_char
        rows={a['name']:a for a in serialize_char(self.a,self.alice)['abilities']}
        self.assertEqual(rows['Удар']['hit_bonus'],1);self.assertEqual(rows['Молния']['hit_bonus'],1)
        self.assertEqual(rows['Камень']['hit_bonus'],0)
        self.assertEqual(rows['Молния']['formula'],'1к8 +1');self.assertEqual(rows['Удар']['formula'],'1к6')
        self.post(self.alice,{'op':'focus.select','character':self.a.id,'item':0})
        self.a.refresh_from_db();self.assertEqual(formula(self.a,magic),'1к8')
        self.post(self.bob,{'op':'focus.select','character':self.a.id,'item':focus.id},403)

    def test_water_nature_fixed_healing_and_undo(self):
        water=self.charm('Малое зачарование воды');nature=self.charm('Малое зачарование природы')
        Item.objects.create(character=self.a,name='Доспех',equipped=True,data={'item_type':'armor','enchantments':[water.id]})
        Item.objects.create(character=self.a,name='Фокус',equipped=True,data={'item_type':'focus','enchantments':[nature.id]})
        self.a.runtime['hp']=20;self.a.save()
        scene=self.start();self.a.refresh_from_db();self.assertEqual(self.a.runtime['temp'],5)
        self.post(self.gm,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['temp'],0)
        self.post(self.gm,{'op':'redo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['temp'],5)
        self.post(self.gm,{'op':'hp','character':self.a.id,'mode':'damage','value':7})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],20);self.assertEqual(self.a.runtime['temp'],0)
        self.post(self.gm,{'op':'hp','character':self.a.id,'mode':'damage','value':5})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],16)
        self.post(self.gm,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],20)
        self.assertEqual(self.a.runtime['enchantment_uses']['hp_lost'],2)
        self.post(self.gm,{'op':'redo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],16)

    def test_first_kill_heal_only_once_and_undo(self):
        dark=self.charm('Малое зачарование тьмы')
        Item.objects.create(character=self.a,name='Меч',equipped=True,data={'item_type':'weapon','dice':'1к6','enchantments':[dark.id]})
        self.a.runtime['hp']=10;self.a.save();self.start()
        self.post(self.alice,{'op':'enchantment.kill','character':self.a.id})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],15)
        self.post(self.alice,{'op':'enchantment.kill','character':self.a.id},400)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],10)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],15)

    def test_cold_weapon_hit_miss_and_undo(self):
        cold=self.charm('Малое зачарование холода')
        Item.objects.create(character=self.a,name='Меч',equipped=True,data={'item_type':'weapon','dice':'1к6','enchantments':[cold.id]})
        attack=Entry.objects.create(kind='ability',name='Удар',data={'weapon':True,'formula':'1Ор','damage':True,'action':'free'})
        self.a.abilities.add(attack);self.start()
        p={'op':'ability.use','character':self.a.id,'ability':attack.id,'targets':[self.b.id],'roll_result':'6','outcome':'miss'}
        self.post(self.alice,p);self.b.refresh_from_db();self.assertEqual(computed(self.b)['speed'],6)
        self.post(self.alice,{**p,'outcome':'hit'});self.b.refresh_from_db();self.assertEqual(computed(self.b)['speed'],5)
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db();self.assertEqual(computed(self.b)['speed'],6)

    def test_initiative_pool_permutation_and_enchantment_bonus(self):
        prime=self.charm('Малое изначальное зачарование');air=self.charm('Малое зачарование воздуха');earth=self.charm('Малое зачарование земли')
        Item.objects.create(character=self.a,name='Доспех',equipped=True,data={'item_type':'armor','enchantments':[prime.id,air.id,earth.id]})
        self.a.stats['dex']=14;self.a.save()
        p={'op':'scene.start','session':self.session.id,'roll_pool':[8,6], 'assigned_rolls':{str(self.a.id):1,str(self.b.id):0}}
        self.post(self.gm,{**p,'assigned_rolls':{str(self.a.id):0,str(self.b.id):0}},400)
        self.post(self.gm,{**p,'roll_pool':[13,6]},400)
        self.assertEqual(Scene.objects.count(),0)
        result=self.post(self.gm,p);scene=Scene.objects.get(pk=result['id'])
        self.assertEqual(scene.state['initiative'],{str(self.a.id):11,str(self.b.id):8})
        self.assertEqual(scene.state['order'],[self.a.id,self.b.id])
        self.assertEqual(computed(self.a)['speed'],7)
        self.assertEqual(computed(self.a)['forced_movement_reduction'],1)

    def test_enchantment_knowledge_permissions(self):
        light=self.charm('Малое зачарование света')
        self.post(self.bob,{'op':'enchantment.learn','character':self.a.id,'entry':light.id},403)
        self.post(self.alice,{'op':'enchantment.learn','character':self.a.id,'entry':light.id})
        self.assertTrue(self.a.abilities.filter(pk=light.id).exists())
        self.post(self.alice,{'op':'enchantment.learn','character':self.a.id,'entry':light.id,'remove':True})
        self.assertFalse(self.a.abilities.filter(pk=light.id).exists())

    def test_custom_item_bonuses_do_not_leak_between_weapon_and_focus(self):
        weapon=Item.objects.create(character=self.a,name='Меч',equipped=True,data={'item_type':'weapon','dice':'1к6','effects':[{'stat':'hit','value':2},{'stat':'damage','value':4}]})
        focus=Item.objects.create(character=self.a,name='Фокус',equipped=True,data={'item_type':'focus','effects':[{'stat':'hit','value':1},{'stat':'damage','value':3}]})
        Item.objects.create(character=self.a,name='Другой фокус',equipped=True,data={'item_type':'focus','effects':[{'stat':'hit','value':20},{'stat':'damage','value':30}]})
        attack=Entry.objects.create(kind='ability',name='Удар',data={'weapon':True,'formula':'1Ор','damage':True})
        magic=Entry.objects.create(kind='ability',name='Огонь',data={'school_name':'Огонь','formula':'1к8','damage':True})
        self.a.abilities.add(attack,magic)
        from .views import serialize_char
        rows={a['name']:a for a in serialize_char(self.a,self.alice)['abilities']}
        self.assertEqual(rows['Удар']['hit_bonus'],2);self.assertEqual(rows['Удар']['formula'],'1к6 +4')
        self.assertEqual(rows['Огонь']['hit_bonus'],1);self.assertEqual(rows['Огонь']['formula'],'1к8 +3')

    def test_equipping_nature_later_cannot_restore_previously_lost_hp(self):
        nature=self.charm('Малое зачарование природы')
        focus=Item.objects.create(character=self.a,name='Фокус',equipped=False,data={'item_type':'focus','enchantments':[nature.id]})
        self.a.runtime['hp']=20;self.a.save();self.start()
        self.post(self.gm,{'op':'hp','character':self.a.id,'mode':'damage','value':3})
        self.post(self.alice,{'op':'item.equip','id':focus.id})
        self.post(self.gm,{'op':'hp','character':self.a.id,'mode':'damage','value':2})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],15)

    def test_custom_enchantment_profile_validation(self):
        self.post(self.gm,{'op':'entry.save','kind':'ability','name':'Свои чары','data':{'enchantment':{'types':['weapon'],'damage':'wrong'}}},400)
        self.post(self.gm,{'op':'entry.save','kind':'ability','name':'Свои чары','data':{'enchantment':{'types':['weapon'],'damage':2}}})
        custom=Entry.objects.get(name='Свои чары')
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Клинок','quantity':1,'data':{'item_type':'weapon','enchantments':[custom.id]}})

    def test_ritual_pool_waits_validates_cleanses_and_master_controls_hp(self):
        ritual=Entry.objects.create(kind='ability',name='Ритуал восстановления',data={'action':'main','circle':3,'rolls':True})
        self.a.level=8;self.a.abilities.add(ritual);self.a.runtime['hp']=10;self.a.save()
        self.b.runtime.update(hp=10,effects=[{'key':'poison','name':'Яд','stat':'status','value':2,'duration':'turns','remaining':3}]);self.b.save()
        self.start()
        p={'op':'ability.use','character':self.a.id,'ability':ritual.id,'outcome':'hit',
           'dice':[2]*9,'allocations':[{'character':self.a.id,'hp':5},{'character':self.b.id,'hp':8,'remove':['poison']}]}
        self.post(self.alice,{**p,'dice':[2]*8},400)
        self.post(self.alice,{**p,'allocations':[{'character':self.a.id,'hp':19}]},400)
        self.post(self.alice,{**p,'allocations':[{'character':self.b.id,'hp':0,'remove':['gone']}]},400)
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['main'],1)
        self.post(self.alice,p);self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],0);self.assertEqual(self.b.runtime['effects'],[])
        self.assertEqual(self.a.runtime['hp'],10);self.assertEqual(self.b.runtime['hp'],10)
        key=next(iter(self.a.runtime['pending_heals']))
        confirm={'op':'healing.confirm','character':self.a.id,'pending':key}
        self.post(self.alice,confirm,403)
        self.post(self.gm,confirm);self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['hp'],15);self.assertEqual(self.b.runtime['hp'],18)
        self.post(self.gm,confirm,400)
        self.post(self.alice,{'op':'undo'},400)
        self.post(self.gm,{'op':'undo'});self.post(self.alice,{'op':'undo'})
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],1);self.assertEqual(self.b.runtime['effects'][0]['key'],'poison')
        self.assertFalse(self.a.runtime.get('pending_heals'))
        self.post(self.alice,{'op':'redo'});self.post(self.gm,{'op':'redo'})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],15)

    def test_heavens_assigns_whole_odd_dice_and_keeps_monster_damage_external(self):
        a=Entry.objects.create(kind='ability',name='Исход небес',data={'action':'main','circle':2,'rolls':True})
        self.a.level=8;self.a.abilities.add(a);self.a.save();self.start()
        p={'op':'ability.use','character':self.a.id,'ability':a.id,'outcome':'hit','dice':[1,2,3,4,5,6],
           'dice_targets':[self.a.id,None,self.b.id,None,self.b.id,None]}
        self.post(self.alice,{**p,'dice_targets':[self.a.id,self.a.id,self.b.id,None,self.b.id,None]},400)
        self.post(self.alice,{**p,'outcome':'critical'},400)
        self.post(self.alice,p)
        pool=Event.objects.latest('id').inputs['roll_pool']
        self.assertEqual(pool['damage_pool'],12);self.assertEqual(pool['healing_pool'],9)
        self.assertEqual(pool['allocations'],[{'character':self.a.id,'hp':1,'remove':[]},{'character':self.b.id,'hp':8,'remove':[]}])

    def test_end_battle_discards_pending_healing_and_undo_restores_it(self):
        a=Entry.objects.create(kind='ability',name='Ритуал восстановления',data={'action':'main','rolls':True})
        self.a.abilities.add(a);scene=self.start()
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':a.id,'dice':[1]*9,'allocations':[{'character':self.b.id,'hp':9}]})
        self.a.refresh_from_db();key=next(iter(self.a.runtime['pending_heals']))
        self.post(self.gm,{'op':'scene.end','scene':scene.id,'version':scene.state})
        self.post(self.gm,{'op':'healing.confirm','character':self.a.id,'pending':key},400)
        self.post(self.gm,{'op':'undo'})
        self.post(self.gm,{'op':'healing.confirm','character':self.a.id,'pending':key})
        self.b.refresh_from_db();self.assertLessEqual(self.b.runtime['hp'],computed(self.b)['max_hp'])

    def test_master_can_dismiss_already_manually_applied_healing(self):
        a=Entry.objects.create(kind='ability',name='Ритуал восстановления',data={'action':'main','rolls':True})
        self.a.abilities.add(a);self.start()
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':a.id,'dice':[1]*9,'allocations':[{'character':self.b.id,'hp':9}]})
        self.a.refresh_from_db();key=next(iter(self.a.runtime['pending_heals']))
        self.b.refresh_from_db();hp=self.b.runtime['hp']
        self.post(self.alice,{'op':'healing.dismiss','character':self.a.id,'pending':key},403)
        self.post(self.gm,{'op':'healing.dismiss','character':self.a.id,'pending':key})
        self.a.refresh_from_db();self.b.refresh_from_db();self.assertFalse(self.a.runtime['pending_heals']);self.assertEqual(self.b.runtime['hp'],hp)
        self.post(self.gm,{'op':'undo'});self.a.refresh_from_db();self.assertIn(key,self.a.runtime['pending_heals'])

    def test_private_knowledge_hidden_from_other_players_and_master(self):
        from .models import Knowledge
        p={'op':'knowledge.save','character':self.a.id,'kind':'contact','title':'Тайный связной','body':'Секрет','location':'Под мостом','details':'Союзник','tags':['связи'],'private':True}
        result=self.post(self.alice,p);row=Knowledge.objects.get(pk=result['id'])
        for user in [self.bob,self.gm]:
            self.client.force_login(user)
            character=next(c for c in self.client.get('/api/state/').json()['characters'] if c['id']==self.a.id)
            self.assertEqual(character['knowledge'],[])
            self.post(user,{**p,'id':row.id,'revision':1,'private':False},403)
            self.post(user,{'op':'knowledge.archive','id':row.id,'revision':1,'archived':True},403)
        self.client.force_login(self.alice)
        own=next(c for c in self.client.get('/api/state/').json()['characters'] if c['id']==self.a.id)
        self.assertEqual(own['knowledge'][0]['body'],'Секрет')
        self.post(self.alice,{**p,'id':row.id,'revision':1,'private':False})
        self.client.force_login(self.bob)
        shared=next(c for c in self.client.get('/api/state/').json()['characters'] if c['id']==self.a.id)
        self.assertEqual(shared['knowledge'][0]['title'],'Тайный связной')
        self.post(self.bob,{**p,'id':row.id,'revision':2},403)
        self.post(self.gm,{**p,'id':row.id,'revision':2,'private':False,'title':'Открытый контакт'})

    def test_knowledge_conflicts_and_archive_restore(self):
        from .models import Knowledge
        p={'op':'knowledge.save','character':self.a.id,'kind':'lore','title':'Руины','private':True,'body':'Первая версия'}
        result=self.post(self.alice,p);pk=result['id']
        self.post(self.alice,{**p,'id':pk,'revision':1,'body':'Новая версия'})
        self.post(self.alice,{**p,'id':pk,'revision':1,'body':'Старая вкладка'},400)
        self.assertEqual(Knowledge.objects.get(pk=pk).body,'Новая версия')
        self.post(self.alice,{'op':'knowledge.archive','id':pk,'revision':2,'archived':True})
        self.post(self.alice,{'op':'knowledge.archive','id':pk,'revision':2,'archived':False},400)
        self.post(self.alice,{'op':'knowledge.archive','id':pk,'revision':3,'archived':False})
        row=Knowledge.objects.get(pk=pk);self.assertEqual(row.revision,4);self.assertFalse(row.archived)

    def test_recipe_source_and_freeform_knowledge(self):
        from .models import Knowledge
        recipe=Entry.objects.create(kind='ability',name='Эликсир',description='Компоненты и время',data={'book_group':'craft','category':'noncombat'})
        p={'op':'knowledge.save','character':self.a.id,'kind':'recipe','title':'Изученный эликсир','private':False,
           'entry':recipe.id,'location':'Алхимик','details':'10 мер пыли','body':'Личная пометка','tags':['алхимия','алхимия',' зелье ']}
        result=self.post(self.alice,p);row=Knowledge.objects.get(pk=result['id'])
        self.assertEqual(row.entry_id,recipe.id);self.assertEqual(row.tags,['алхимия','зелье'])
        self.post(self.alice,{**p,'id':row.id,'revision':1,'entry':None,'title':'Собственный рецепт'})
        row.refresh_from_db();self.assertIsNone(row.entry_id)
        self.post(self.alice,{**p,'kind':'contact'},400)
        self.post(self.alice,{**p,'entry':self.bless.id},400)

    def test_knowledge_validation_and_master_cannot_create_private_for_player(self):
        p={'op':'knowledge.save','character':self.a.id,'kind':'contact','title':'Друг','private':True}
        self.post(self.gm,p,403)
        for invalid in [{'title':''},{'kind':'unknown'},{'private':'true'},{'tags':['x'*41]},{'body':'x'*30001}]:
            self.post(self.alice,{**p,**invalid},400)
        self.post(self.gm,{**p,'private':False})

    def test_partial_inventory_transfer_preserves_properties_and_undo(self):
        item=Item.objects.create(character=self.a,name='Зелье',quantity=5,data={'item_type':'consumable','description':'Особое зелье','custom':{'maker':'А'}})
        self.post(self.alice,{'op':'item.transfer','id':item.id,'revision':item.revision,'quantity':2,'character':self.b.id})
        item.refresh_from_db();received=self.b.items.get(archived=False)
        self.assertEqual(item.quantity,3);self.assertEqual(received.quantity,2);self.assertEqual(received.data,item.data)
        self.post(self.alice,{'op':'undo'});item.refresh_from_db();received.refresh_from_db()
        self.assertEqual(item.quantity,5);self.assertTrue(received.archived);self.assertEqual(received.quantity,0)
        self.post(self.alice,{'op':'redo'});received.refresh_from_db();self.assertFalse(received.archived);self.assertEqual(received.quantity,2)
        self.post(self.bob,{'op':'item.consume','id':received.id,'revision':received.revision,'quantity':1})
        self.post(self.alice,{'op':'undo'},400)
        self.post(self.bob,{'op':'undo'});self.post(self.alice,{'op':'undo'})
        item.refresh_from_db();self.assertEqual(item.quantity,5)

    def test_inventory_create_edit_delete_and_legacy_equip_undo(self):
        p={'op':'item.save','character':self.a.id,'name':'Клинок','quantity':1,'data':{'item_type':'weapon','dice':'1к6'},'equipped':True}
        result=self.post(self.alice,p);item=Item.objects.get(pk=result['id'])
        self.post(self.alice,{'op':'undo'});item.refresh_from_db();self.assertTrue(item.archived)
        self.post(self.alice,{'op':'redo'});item.refresh_from_db();self.assertFalse(item.archived)
        self.post(self.alice,{**p,'id':item.id,'revision':item.revision,'name':'Новый клинок','data':{'item_type':'weapon','dice':'1к8'}})
        self.post(self.alice,{'op':'undo'});item.refresh_from_db();self.assertEqual(item.name,'Клинок');self.assertEqual(item.data['dice'],'1к6')
        self.post(self.alice,{'op':'item.delete','id':item.id,'revision':item.revision});item.refresh_from_db();self.assertTrue(item.archived)
        self.client.force_login(self.alice)
        sheet=next(c for c in self.client.get('/api/state/').json()['characters'] if c['id']==self.a.id)
        self.assertEqual(sheet['items'],[])
        self.post(self.alice,{'op':'undo'});item.refresh_from_db();self.assertFalse(item.archived);self.assertTrue(item.equipped)
        item.equipped=False;item.save()
        Event.objects.create(actor=self.alice,label='Старая экипировка',before={f'item:{item.id}':{'equipped':True}},after={f'item:{item.id}':{'equipped':False}})
        self.post(self.alice,{'op':'undo'});item.refresh_from_db();self.assertTrue(item.equipped)

    def test_stock_stale_versions_and_invalid_quantities(self):
        item=Item.objects.create(campaign=self.campaign,name='Золото',quantity=20,data={'item_type':'currency'})
        p={'op':'item.consume','id':item.id,'revision':1,'quantity':5}
        self.post(self.alice,p);self.post(self.bob,p,400)
        item.refresh_from_db();self.assertEqual(item.quantity,15)
        for value in [0,-1,16,1.5,True]:self.post(self.alice,{**p,'revision':item.revision,'quantity':value},400)
        stranger=User.objects.create_user('outsider')
        self.post(stranger,{**p,'revision':item.revision},403)
        self.post(self.alice,{'op':'undo'});item.refresh_from_db();self.assertEqual(item.quantity,20)

    def test_transfer_recipient_permissions_and_combat_restrictions(self):
        item=Item.objects.create(character=self.a,name='Верёвка',quantity=3)
        stranger=User.objects.create_user('outsider')
        other=Character.objects.create(owner=stranger,name='Чужой',runtime=fresh())
        self.post(self.alice,{'op':'item.transfer','id':item.id,'character':other.id,'quantity':1},403)
        self.post(self.alice,{'op':'item.transfer','id':item.id,'character':self.a.id,'quantity':1},400)
        self.post(self.alice,{'op':'item.transfer','id':item.id,'character':self.b.id,'quantity':4},400)
        self.start()
        self.post(self.alice,{'op':'item.transfer','id':item.id,'character':self.b.id,'quantity':1},400)
        stock=Item.objects.create(campaign=self.campaign,name='Зелье',quantity=3)
        self.post(self.alice,{'op':'item.transfer','id':stock.id,'character':self.b.id,'quantity':1},400)

    def test_equipment_undo_respects_battle_start_dependency(self):
        result=self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Доспех','quantity':1,'equipped':True,'data':{'item_type':'armor','armor':3}})
        self.start()
        self.post(self.alice,{'op':'undo'},400)
        self.post(self.gm,{'op':'undo'});self.post(self.alice,{'op':'undo'})
        self.assertTrue(Item.objects.get(pk=result['id']).archived)

    def test_saving_armor_equips_only_one_and_undo_restores_previous(self):
        old=Item.objects.create(character=self.a,name='Старый доспех',equipped=True,data={'item_type':'armor','armor':2})
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Новый доспех','quantity':1,'equipped':True,'data':{'item_type':'armor','armor':4}})
        old.refresh_from_db();self.assertFalse(old.equipped);self.assertEqual(computed(self.a)['ac'],9)
        self.post(self.alice,{'op':'undo'});old.refresh_from_db();self.assertTrue(old.equipped);self.assertEqual(computed(self.a)['ac'],7)

    def test_archived_item_never_contributes_to_character_calculations(self):
        item=Item.objects.create(character=self.a,name='Архивный клинок',quantity=1,equipped=True,archived=True,
                                 data={'dice':'1к6','armor':4,'effects':[{'stat':'hit','value':20}]})
        calc=computed(self.a);self.assertEqual(calc['hit'],0);self.assertEqual(calc['ac'],5);self.assertTrue(calc['unarmed'])
        self.post(self.alice,{'op':'weapon.select','character':self.a.id,'item':item.id},404)

    def prepare_crafter(self,name,recipe):
        craft=Entry.objects.create(kind='craft',name=name)
        self.a.info['craft_ids']=[craft.id];self.a.abilities.add(recipe);self.a.save()

    def test_enchanting_consumes_materials_and_splits_one_item_atomically(self):
        fire=self.charm('Малое зачарование огня');self.prepare_crafter('Зачарователь',fire)
        target=Item.objects.create(character=self.a,name='Кинжал',quantity=3,data={'item_type':'weapon','dice':'1к4','families':['Кинжалы']})
        dust=Item.objects.create(character=self.a,name='Пыль',quantity=100,data={'item_type':'material','material_kind':'magic_dust'})
        component=Item.objects.create(campaign=self.campaign,name='Огненный камень',quantity=2,data={'item_type':'material','material_kind':'elemental','element':'Огонь'})
        p={'op':'craft.apply','character':self.a.id,'recipe':fire.id,'item':target.id,'item_revision':1,
           'supplies':[{'item':dust.id,'revision':1,'quantity':50,'role':'dust'},{'item':component.id,'revision':1,'quantity':1,'role':'component'}]}
        result=self.post(self.alice,p);made=Item.objects.get(pk=result['id'])
        target.refresh_from_db();dust.refresh_from_db();component.refresh_from_db()
        self.assertEqual((target.quantity,made.quantity,dust.quantity,component.quantity),(2,1,50,1))
        self.assertEqual(made.data['enchantments'],[fire.id]);self.assertNotEqual(made.id,target.id)
        self.post(self.alice,{'op':'undo'});target.refresh_from_db();dust.refresh_from_db();made.refresh_from_db();component.refresh_from_db()
        self.assertEqual((target.quantity,dust.quantity,component.quantity),(3,100,2));self.assertTrue(made.archived)
        self.post(self.alice,{'op':'redo'});made.refresh_from_db();self.assertFalse(made.archived)
        self.post(self.bob,{'op':'item.consume','id':component.id,'quantity':1})
        self.post(self.alice,{'op':'undo'},400)

    def test_crafting_rejects_short_supplies_wrong_element_and_stale_stock(self):
        fire=self.charm('Малое зачарование огня');self.prepare_crafter('Зачарователь',fire)
        target=Item.objects.create(character=self.a,name='Клинок',data={'item_type':'weapon','dice':'1к6'})
        dust=Item.objects.create(character=self.a,name='Пыль',quantity=100,data={'material_kind':'magic_dust'})
        wrong=Item.objects.create(character=self.a,name='Водный камень',quantity=2,data={'material_kind':'elemental','element':'Вода'})
        p={'op':'craft.apply','character':self.a.id,'recipe':fire.id,'item':target.id,'item_revision':1,'supplies':[]}
        self.post(self.alice,p,400)
        self.post(self.alice,{**p,'supplies':[{'item':dust.id,'revision':1,'quantity':50,'role':'dust'},{'item':wrong.id,'revision':1,'quantity':1,'role':'component'}]},400)
        self.post(self.alice,{**p,'item_revision':0},400)
        self.post(self.bob,p,403)
        dust.refresh_from_db();self.assertEqual(dust.quantity,100);self.assertEqual(Event.objects.count(),0)

    def test_crafting_rejects_same_stock_with_differently_formatted_ids(self):
        fire=self.charm('Малое зачарование огня');self.prepare_crafter('Зачарователь',fire)
        target=Item.objects.create(character=self.a,name='Клинок',data={'item_type':'weapon','dice':'1к6'})
        dust=Item.objects.create(character=self.a,name='Пыль',quantity=25,data={'material_kind':'magic_dust'})
        component=Item.objects.create(character=self.a,name='Камень',quantity=1,data={'material_kind':'elemental','element':'Огонь'})
        p={'op':'craft.apply','character':self.a.id,'recipe':fire.id,'item':target.id,'item_revision':1,
           'supplies':[{'item':dust.id,'revision':1,'quantity':25,'role':'dust'},
                       {'item':str(dust.id),'revision':1,'quantity':25,'role':'dust'},
                       {'item':component.id,'revision':1,'quantity':1,'role':'component'}]}
        self.post(self.alice,p,400)
        dust.refresh_from_db();component.refresh_from_db();target.refresh_from_db()
        self.assertEqual(dust.quantity,25);self.assertEqual(component.quantity,1)
        self.assertNotIn('enchantments',target.data);self.assertEqual(Event.objects.count(),0)
        balanced=self.charm('Сбалансированный');self.prepare_crafter('Оружейник',balanced)
        target.data['families']=['Мечи'];target.save()
        self.post(self.alice,{**p,'recipe':balanced.id,'supplies':[{'item':str(target.id),'revision':1,'quantity':1}]},400)
        target.refresh_from_db();self.assertEqual(target.quantity,1);self.assertNotIn('upgrades',target.data)

    def test_weaponsmith_bonuses_and_range_are_applied_to_selected_weapon(self):
        from .views import serialize_char
        balanced=self.charm('Сбалансированный');heavy=self.charm('Утяжеленный');taut=self.charm('Тугой');piercing=self.charm('Пробивающий')
        self.prepare_crafter('Оружейник',balanced);self.a.abilities.add(heavy,taut,piercing)
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'formula':'1Ор','damage':True,'keywords':['Оружие','Ближний']})
        for name,family,recipe,expected_hit,expected_crit,expected_range,armored in [
            ('Меч','Мечи',balanced,1,0,'Ближний',None),('Топор','Топоры',heavy,0,1,'Ближний',None),
            ('Лук','Луки',taut,0,0,'Дальнобойный 15',None),('Молот','Молоты',piercing,0,0,'Ближний',1)]:
            item=Item.objects.create(character=self.a,name=name,equipped=True,data={'item_type':'weapon','dice':'1к6','families':[family],'keywords':[family]+(['Дальнобойный 10'] if family=='Луки' else [])})
            self.post(self.alice,{'op':'craft.apply','character':self.a.id,'recipe':recipe.id,'item':item.id,'item_revision':1})
            self.a.runtime['weapon_id']=item.id;self.a.save()
            calc=computed(self.a);row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==attack.id)
            self.assertEqual(row['hit_bonus'],expected_hit);self.assertEqual(calc['crit'],expected_crit)
            self.assertEqual(row['data']['range'],expected_range);self.assertEqual(row['armored_hit_bonus'],armored)
            if expected_crit:self.assertEqual(row['critical'],'3к6')
            item.refresh_from_db()
            self.post(self.alice,{'op':'craft.apply','character':self.a.id,'recipe':recipe.id,'item':item.id,'item_revision':item.revision},400)

    def test_ranged_and_thrown_standard_attacks_do_not_get_melee_boulder(self):
        boulder=self.charm('Глыба');boulder.data={'category':'passive','stat':'wis'};boulder.save();self.a.abilities.add(boulder)
        self.a.stats['wis']=16;self.a.save()
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'formula':'1Ор','damage':True,'keywords':['Ближний']})
        item=Item.objects.create(character=self.a,name='Лук',equipped=True,data={'item_type':'weapon','dice':'1к6','keywords':['Дальнобойный 10']})
        self.assertEqual(formula(self.a,attack),'1к6')
        item.data={'item_type':'weapon','dice':'1к4','keywords':['Метательное 5']};item.save()
        self.assertEqual(formula(self.a,attack),'1к4 +3 [Земля]')
        self.post(self.alice,{'op':'attack.mode','character':self.a.id,'mode':'ranged'})
        self.a.refresh_from_db();self.assertEqual(formula(self.a,attack),'1к4')
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(formula(self.a,attack),'1к4 +3 [Земля]')

    def test_crafting_requires_known_recipe_and_selected_craft(self):
        balanced=self.charm('Сбалансированный')
        target=Item.objects.create(character=self.a,name='Меч',data={'item_type':'weapon','dice':'1к6','families':['Мечи']})
        p={'op':'craft.apply','character':self.a.id,'recipe':balanced.id,'item':target.id,'item_revision':1}
        self.post(self.alice,p,400)
        self.prepare_crafter('Оружейник',balanced)
        self.start();self.post(self.alice,p,400)

    def test_alchemy_production_spends_materials_and_can_be_undone(self):
        for name,product in [('Малое зелье лечения','healing_potion'),('Малый яд','poison'),('Масло точности','accuracy_oil')]:
            recipe=self.charm(name);self.prepare_crafter('Алхимик',recipe)
            material=Item.objects.create(campaign=self.campaign,name='Травы',quantity=3,data={'item_type':'material'})
            p={'op':'craft.apply','character':self.a.id,'recipe':recipe.id,'prepared':True,
               'supplies':[{'item':material.id,'revision':material.revision,'quantity':2}]}
            self.post(self.alice,{**p,'prepared':False},400)
            made=Item.objects.get(pk=self.post(self.alice,p)['id']);material.refresh_from_db()
            self.assertEqual(material.quantity,1);self.assertEqual(made.quantity,1)
            self.assertEqual(made.character,self.a);self.assertEqual(made.data['alchemy'],product)
            self.assertEqual(made.data['preparation_hours'],3)
            self.post(self.alice,{'op':'undo'});made.refresh_from_db();material.refresh_from_db()
            self.assertTrue(made.archived);self.assertEqual(material.quantity,3)
            self.post(self.alice,{'op':'redo'});made.refresh_from_db();self.assertFalse(made.archived)
            self.post(self.alice,{'op':'item.consume','id':made.id,'quantity':1})
            self.post(self.alice,{'op':'undo'});self.post(self.alice,{'op':'undo'})
            made.refresh_from_db();self.assertTrue(made.archived)

    def test_weapon_upgrade_validation_and_material_types(self):
        balanced=self.charm('Сбалансированный')
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Лук','data':{'item_type':'weapon','families':['Луки'],'upgrades':[balanced.id]}},400)
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Камень','data':{'item_type':'material','material_kind':'elemental','element':'Нет такой'}},400)
        self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Пыль','quantity':50,'data':{'item_type':'material','material_kind':'magic_dust'}})

    def test_material_cannot_be_equipped_and_custom_upgrade_profile(self):
        result=self.post(self.alice,{'op':'item.save','character':self.a.id,'name':'Пыль','quantity':50,'equipped':True,'data':{'item_type':'material','material_kind':'magic_dust'}})
        item=Item.objects.get(pk=result['id']);self.assertFalse(item.equipped)
        self.post(self.alice,{'op':'item.equip','id':item.id},400)
        p={'op':'entry.save','kind':'ability','name':'Особая ковка','data':{'weapon_upgrade':{'families':['Мечи'],'hit':2}}}
        self.post(self.gm,p)
        custom=Entry.objects.get(name='Особая ковка');self.prepare_crafter('Оружейник',custom)
        weapon=Item.objects.create(character=self.a,name='Меч',equipped=True,data={'item_type':'weapon','dice':'1к6','families':['Мечи']})
        self.post(self.alice,{'op':'craft.apply','character':self.a.id,'recipe':custom.id,'item':weapon.id,'item_revision':weapon.revision})
        self.assertEqual(computed(self.a)['hit'],2)
        self.post(self.gm,{**p,'data':{'weapon_upgrade':{'families':['Мечи'],'hit':'bad'}}},400)

    def test_keyword_bonuses_follow_standard_attack_range(self):
        from .views import serialize_char
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'formula':'1Ор','damage':True,'keywords':['Ближний']})
        Item.objects.create(character=self.a,name='Кинжал',equipped=True,data={'item_type':'weapon','dice':'1к4','keywords':['Метательное 5']})
        self.a.runtime['effects']=[{'key':'melee-hit','stat':'hit','keyword':'Ближний','value':2},{'key':'melee-damage','stat':'damage','keyword':'Ближний','value':4},{'key':'ranged-hit','stat':'hit','keyword':'Дальнобойный','value':3}];self.a.save()
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==attack.id)
        self.assertEqual(row['hit_bonus'],2);self.assertEqual(row['formula'],'1к4 +4')
        self.post(self.alice,{'op':'attack.mode','character':self.a.id,'mode':'ranged'});self.a.refresh_from_db()
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==attack.id)
        self.assertEqual(row['hit_bonus'],3);self.assertEqual(row['formula'],'1к4');self.assertEqual(row['data']['range'],'Дальнобойный 5')

    def test_accuracy_oil_splits_weapon_and_tracks_selected_equipment(self):
        from .enchantments import ability_bonus
        oil=Item.objects.create(character=self.a,name='Масло точности',quantity=2,data={'item_type':'consumable'})
        weapon=Item.objects.create(character=self.a,name='Кинжал',quantity=2,equipped=True,data={'item_type':'weapon','dice':'1к4'})
        other=Item.objects.create(character=self.a,name='Другой клинок',equipped=True,data={'item_type':'weapon','dice':'1к6'})
        p={'op':'alchemy.oil','character':self.a.id,'id':oil.id,'revision':1,'weapon':weapon.id,'weapon_revision':1}
        result=Item.objects.get(pk=self.post(self.alice,p)['id'])
        self.a.refresh_from_db();weapon.refresh_from_db();oil.refresh_from_db()
        self.assertEqual((weapon.quantity,result.quantity,oil.quantity),(1,1,1))
        self.assertFalse(weapon.equipped);self.assertTrue(result.equipped)
        self.assertEqual(computed(self.a)['weapon_id'],result.id)
        attack=Entry.objects.create(kind='ability',name='Атака',data={'weapon':True})
        spell=Entry.objects.create(kind='ability',name='Магия',data={'keywords':['Магическое']})
        self.assertEqual(ability_bonus(computed(self.a),attack,'hit'),1)
        self.assertEqual(ability_bonus(computed(self.a),spell,'hit'),0)
        self.post(self.alice,{'op':'weapon.select','character':self.a.id,'item':other.id})
        self.a.refresh_from_db();self.assertEqual(ability_bonus(computed(self.a),attack,'hit'),0)
        self.post(self.alice,{'op':'undo'});self.post(self.alice,{'op':'undo'})
        oil.refresh_from_db();weapon.refresh_from_db();result.refresh_from_db()
        self.assertEqual(oil.quantity,2);self.assertEqual(weapon.quantity,2)
        self.assertTrue(weapon.equipped);self.assertTrue(result.archived)
        self.post(self.alice,{'op':'redo'});result.refresh_from_db();self.assertTrue(result.data['accuracy_oil'])

    def test_accuracy_oil_expires_after_one_battle_and_end_can_be_undone(self):
        oil=Item.objects.create(character=self.a,name='Масло точности',quantity=2,data={'item_type':'consumable'})
        weapon=Item.objects.create(character=self.a,name='Клинок',equipped=True,data={'item_type':'weapon','dice':'1к6'})
        scene=self.start()
        p={'op':'alchemy.oil','character':self.a.id,'id':oil.id,'revision':1,'weapon':weapon.id,'weapon_revision':1}
        self.post(self.alice,p);self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['main'],0)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['main'],1)
        self.post(self.alice,{'op':'redo'})
        self.post(self.gm,{'op':'scene.end','scene':scene.id,'version':scene.state})
        weapon.refresh_from_db();self.assertNotIn('accuracy_oil',weapon.data)
        self.post(self.gm,{'op':'undo'});weapon.refresh_from_db();self.assertTrue(weapon.data['accuracy_oil'])
        self.post(self.gm,{'op':'redo'});weapon.refresh_from_db();self.assertNotIn('accuracy_oil',weapon.data)
        scene=self.start();self.a.refresh_from_db();self.assertEqual(computed(self.a)['hit'],0)

    def test_accuracy_oil_rejects_stale_repeat_foreign_and_out_of_turn_use(self):
        oil=Item.objects.create(character=self.a,name='Масло точности',quantity=2,data={'item_type':'consumable'})
        weapon=Item.objects.create(character=self.a,name='Клинок',data={'item_type':'weapon','dice':'1к6'})
        p={'op':'alchemy.oil','character':self.a.id,'id':oil.id,'revision':1,'weapon':weapon.id,'weapon_revision':1}
        self.post(self.bob,p,403);self.post(self.alice,{**p,'revision':0},400)
        self.post(self.alice,p);weapon.refresh_from_db();oil.refresh_from_db()
        self.post(self.alice,{**p,'revision':oil.revision,'weapon_revision':weapon.revision},400)
        self.post(self.alice,{'op':'undo'});oil.refresh_from_db();weapon.refresh_from_db()
        scene=self.start();self.turn(scene,self.alice)
        from .views import serialize_char
        self.a.refresh_from_db()
        self.assertEqual(serialize_char(self.a,self.alice)['main_action_reason'],'Ход другого персонажа')
        self.post(self.alice,{**p,'revision':oil.revision,'weapon_revision':weapon.revision},400)
        oil.refresh_from_db();self.assertEqual(oil.quantity,2)

    def ready(self,action='main'):
        return self.post(self.alice,{'op':'action.ready','character':self.a.id,'action':action,'condition':'Когда союзник подаст знак'})

    def test_readied_ability_uses_reserved_action_and_shifts_only_next_round(self):
        scene=self.start();self.ready();self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],0);self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.turn(scene,self.alice)
        p={'op':'ability.use','character':self.a.id,'ability':self.bless.id,'targets':[self.b.id],
           'use_ready':True,'triggered':True,'dex_roll':5,'outcome':'hit'}
        self.post(self.alice,p);scene.refresh_from_db();self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(scene.state['order'],[self.a.id,self.b.id])
        self.assertEqual(scene.state['turn'],1);self.assertEqual(self.b.runtime['temp'],5)
        self.assertEqual(self.a.runtime['actions']['main'],0);self.assertNotIn('readied',self.a.runtime)
        self.assertEqual(self.a.runtime['initiative_shift']['value'],9)
        self.turn(scene,self.bob);scene.refresh_from_db();self.a.refresh_from_db()
        self.assertEqual(scene.state['order'],[self.b.id,self.a.id]);self.assertEqual(scene.state['turn'],0)
        self.assertEqual(scene.state['initiative'][str(self.a.id)],9)
        self.assertEqual(scene.state['round'],2);self.assertNotIn('initiative_shift',self.a.runtime)
        self.post(self.bob,{'op':'undo'});scene.refresh_from_db();self.a.refresh_from_db()
        self.assertEqual(scene.state['order'],[self.a.id,self.b.id]);self.assertIn('initiative_shift',self.a.runtime)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertIn('readied',self.a.runtime);self.assertEqual(self.b.runtime['temp'],0)

    def test_readied_validation_does_not_spend_reserved_action_or_ability(self):
        scene=self.start();self.ready();self.turn(scene,self.alice)
        p={'op':'ability.use','character':self.a.id,'ability':self.bless.id,'targets':[self.b.id],
           'use_ready':True,'triggered':True,'outcome':'hit'}
        self.post(self.alice,p,400);self.post(self.alice,{**p,'dex_roll':10,'triggered':False},400)
        self.post(self.alice,{**p,'dex_roll':True},400)
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertIn('readied',self.a.runtime);self.assertFalse(self.a.runtime['used']);self.assertEqual(self.b.runtime['temp'],0)
        self.post(self.alice,{**p,'dex_roll':10});self.a.refresh_from_db()
        self.assertNotIn('initiative_shift',self.a.runtime)
        self.post(self.alice,{**p,'dex_roll':10},400)

    def test_readied_action_expires_at_round_end_and_undo_restores_it(self):
        scene=self.start();self.ready('move');self.turn(scene,self.alice);self.turn(scene,self.bob)
        self.a.refresh_from_db();self.assertNotIn('readied',self.a.runtime)
        self.post(self.alice,{'op':'action.perform_ready','character':self.a.id,'triggered':True,'voluntary_fail':True},400)
        self.post(self.bob,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['readied']['action'],'move')
        self.post(self.alice,{'op':'action.perform_ready','character':self.a.id,'triggered':True,'voluntary_fail':True})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['initiative_shift']['after'],self.b.id)

    def test_readied_reservation_requires_minor_and_preserves_unused_charges(self):
        self.start()
        self.post(self.alice,{'op':'action.ready','character':self.a.id,'action':'minor','condition':'Знак'},400)
        self.post(self.alice,{'op':'action.ready','character':self.a.id,'action':'main','condition':''},400)
        self.post(self.bob,{'op':'action.ready','character':self.a.id,'action':'main','condition':'Знак'},403)
        self.ready();self.a.refresh_from_db();self.assertFalse(self.a.runtime['used'])
        self.post(self.alice,{'op':'action.ready','character':self.a.id,'action':'move','condition':'Знак'},400)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],1);self.assertEqual(self.a.runtime['actions']['minor'],1)
        self.post(self.alice,{'op':'action.spend','character':self.a.id,'action':'main','exchange':'minor'})
        self.ready('minor');self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['minor'],0)

    def test_readied_action_cannot_bypass_wrong_action_or_sleep(self):
        scene=self.start();self.ready('move');self.turn(scene,self.alice)
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':self.bless.id,'targets':[self.b.id],
                              'use_ready':True,'triggered':True,'dex_roll':10},400)
        self.a.refresh_from_db();self.a.runtime['effects'].append({'key':'sleep','name':'Сон','value':1});self.a.save()
        self.post(self.alice,{'op':'action.perform_ready','character':self.a.id,'triggered':True,'dex_roll':10},400)

    def test_multiple_readied_actions_can_resolve_in_any_order(self):
        scene=self.start();self.a.refresh_from_db();self.a.runtime['actions']['minor']=2;self.a.save()
        self.ready('main');self.ready('move');self.a.refresh_from_db()
        first=self.a.runtime['readied']['key'];second=self.a.runtime['readied_queue'][0]['key']
        self.turn(scene,self.alice)
        self.post(self.alice,{'op':'action.perform_ready','character':self.a.id,'ready_id':second,'triggered':True,'dex_roll':10})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['readied']['key'],first)
        self.assertFalse(self.a.runtime.get('readied_queue'))
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':self.bless.id,'targets':[self.b.id],
                              'use_ready':True,'ready_id':first,'triggered':True,'dex_roll':10})
        self.a.refresh_from_db();self.assertNotIn('readied',self.a.runtime)

    def test_state_reuses_catalogue_after_character_change(self):
        Entry.objects.create(kind='item',name='Большая справочная запись',description='Описание ' * 10000)
        self.client.force_login(self.alice)
        first=self.client.get('/api/state/');original=first.json();token=original['catalog_revision']
        self.post(self.gm,{'op':'hp','character':self.a.id,'mode':'damage','value':1})
        self.client.force_login(self.alice)
        response=self.client.get('/api/state/',{'catalog_revision':token,'revision':original['revision']})
        data=response.json()
        self.assertNotIn('catalog',data);self.assertNotIn('rules',data)
        self.assertEqual(data['catalog_revision'],token)
        self.assertEqual(next(c for c in data['characters'] if c['id']==self.a.id)['runtime']['hp'],9)
        self.assertLess(len(response.content),len(first.content)//2)
        unchanged=self.client.get('/api/state/',{'revision':data['revision'],'catalog_revision':token}).json()
        self.assertTrue(unchanged['unchanged'])

    def test_catalogue_updates_replace_cached_rules_and_archived_entries(self):
        self.client.force_login(self.alice)
        first=self.client.get('/api/state/').json();token=first['catalog_revision']
        result=self.post(self.gm,{'op':'entry.save','kind':'ability','name':'Особые чары','description':'Первый вариант',
                                 'data':{'enchantment':{'types':['weapon'],'hit':3}}})
        self.client.force_login(self.alice)
        updated=self.client.get('/api/state/',{'catalog_revision':token,'revision':first['revision']}).json()
        self.assertNotEqual(updated['catalog_revision'],token)
        self.assertEqual(next(e for e in updated['rules']['enchantments'] if e['id']==result['id'])['hit'],3)
        token=updated['catalog_revision']
        self.post(self.gm,{'op':'entry.save','id':result['id'],'archive':True})
        self.client.force_login(self.alice)
        archived=self.client.get('/api/state/',{'catalog_revision':token}).json()
        self.assertNotEqual(archived['catalog_revision'],token)
        self.assertNotIn(result['id'],[e['id'] for e in archived['catalog']])
        self.assertNotIn(result['id'],[e['id'] for e in archived['rules']['enchantments']])

    def test_catalogue_full_response_without_cache_and_content_based_revision(self):
        self.client.force_login(self.alice)
        first=self.client.get('/api/state/').json()
        repeat=self.client.get('/api/state/',{'catalog_revision':'unknown'}).json()
        self.assertEqual(first['catalog_revision'],repeat['catalog_revision']);self.assertIn('catalog',repeat)
        self.assertIn('rules',repeat)
        self.bless.data=dict(reversed(list(self.bless.data.items())));self.bless.save()
        same=self.client.get('/api/state/').json()
        self.assertEqual(first['catalog_revision'],same['catalog_revision'])
        self.bless.description='Изменённое описание';self.bless.save()
        updated=self.client.get('/api/state/',{'catalog_revision':first['catalog_revision']}).json()
        self.assertIn('catalog',updated);self.assertNotEqual(first['catalog_revision'],updated['catalog_revision'])

    def test_lightning_reflexes_doubles_reactions_and_refreshes_each_round(self):
        reflex=Entry.objects.create(kind='ability',name='Молниеносные рефлексы',data={'category':'passive','circle':3})
        self.a.abilities.add(reflex)
        self.assertEqual(computed(self.a)['reactions'],2)
        self.a.stats['wis']=16;self.a.save();self.assertEqual(computed(self.a)['reactions'],6)
        scene=self.start();self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['reaction'],6)
        self.turn(scene,self.alice);self.turn(scene,self.bob);self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['reaction'],6)
        reflex.archived=True;reflex.save();self.assertEqual(computed(self.a)['reactions'],3)

    def test_lightning_reflexes_at_will_reaction_once_per_turn_and_undo(self):
        reflex=Entry.objects.create(kind='ability',name='Молниеносные рефлексы',data={'category':'passive'})
        attack=Entry.objects.create(kind='ability',name='Неограниченная искра',data={'circle':0,'damage':True,'formula':'1к6','rolls':True})
        self.a.abilities.add(reflex,attack)
        third=Character.objects.create(owner=self.bob,name='В',runtime=fresh())
        Membership.objects.create(character=third,campaign=self.campaign,squad=self.squad);self.session.characters.add(third)
        scene=self.start()
        p={'op':'ability.use','character':self.a.id,'ability':attack.id,'as_reaction':True,'outcome':'hit','roll_result':'4'}
        self.post(self.alice,p,400)
        self.turn(scene,self.alice)
        self.post(self.alice,{**p,'roll_result':''},400)
        self.post(self.alice,p);self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['reaction'],1);self.assertEqual(self.a.runtime['actions']['main'],1)
        self.post(self.alice,p,400)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['reaction'],2)
        self.assertNotIn('lightning_reflexes',self.a.runtime.get('once_per_turn',{}))
        self.post(self.alice,{'op':'redo'});self.post(self.alice,p,400)
        self.turn(scene,self.bob);self.post(self.alice,{**p,'outcome':'miss'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['reaction'],0)
        self.assertIn('Молниеносные рефлексы',Event.objects.latest('id').label)
        self.post(self.alice,p,400)

    def test_lightning_reflexes_requires_learned_passive_and_at_will_ability(self):
        from .views import serialize_char
        attack=Entry.objects.create(kind='ability',name='Искра',data={'circle':0})
        self.a.abilities.add(attack);scene=self.start();self.turn(scene,self.alice)
        p={'op':'ability.use','character':self.a.id,'ability':attack.id,'as_reaction':True,'outcome':'hit'}
        self.post(self.alice,p,400)
        reflex=Entry.objects.create(kind='ability',name='Молниеносные рефлексы',data={'category':'passive'})
        self.a.abilities.add(reflex)
        self.post(self.alice,{**p,'ability':self.bless.id,'targets':[self.b.id]},400)
        self.post(self.alice,{**p,'use_ready':True},400)
        self.post(self.bob,p,403)
        self.a.refresh_from_db()
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==attack.id)
        self.assertEqual(row['reflex_reason'],'');self.assertEqual(row['reason'],'Ход другого персонажа')
        reflex.archived=True;reflex.save();self.post(self.alice,p,400)


    def mystic_setup(self,double=False):
        passive=Entry.objects.create(kind='ability',name='Мистические стрелы',data={'category':'passive'})
        self.a.abilities.add(passive)
        if double:self.a.abilities.add(Entry.objects.create(kind='ability',name='Двойной заряд',data={'category':'passive'}))
        bow=Item.objects.create(character=self.a,name='Лук',equipped=True,data={'item_type':'weapon','dice':'1к6','families':['Луки'],'keywords':['Дальнобойный 10']})
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'damage':True,'formula':'1Ор'})
        scene=self.start()
        payload={'op':'ability.use','character':self.a.id,'ability':attack.id,'targets':[self.b.id],
                 'mystic_arrows':['frost'],'roll_result':'Попадание 15, урон 4','outcome':'hit'}
        return scene,payload,bow,passive

    def test_mystic_arrow_waits_for_choice_and_physical_roll(self):
        scene,p,bow,passive=self.mystic_setup()
        for extra in [{'mystic_arrows':[]},{'mystic_arrows':['unknown']},{'mystic_arrows':['frost','bind']},
                      {'mystic_arrows':['frost','frost']},{'mystic_arrows':'frost'},{'roll_result':''},
                      {'targets':[self.a.id,self.b.id]}]:
            self.post(self.alice,{**p,**extra},400)
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],1);self.assertEqual(self.a.runtime['mystic_arrows'],0)
        self.assertEqual(self.b.runtime['effects'],[])
        self.post(self.bob,p,403)
        bow.data['families']=['Арбалеты'];bow.save();self.post(self.alice,p,400)
        bow.data['families']=['Луки'];bow.save();passive.archived=True;passive.save();self.post(self.alice,p,400)
        self.post(self.alice,{**p,'mystic_arrows':[]})

    def test_mystic_arrow_exhaustion_miss_and_undo(self):
        from .views import serialize_char
        scene,p,_,_=self.mystic_setup()
        self.post(self.alice,p);self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(computed(self.b)['speed'],3);self.assertEqual(self.b.runtime['hp'],10)
        self.assertEqual(self.a.runtime['mystic_arrows'],1);self.assertEqual(computed(self.a)['hit'],0)
        self.turn(scene,self.alice);self.turn(scene,self.bob)
        self.post(self.alice,{**p,'mystic_arrows':['bind'],'outcome':'miss'})
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['mystic_arrows'],2);self.assertEqual(computed(self.a)['hit'],-1)
        self.assertEqual(computed(self.b)['speed'],3)
        self.assertNotIn('Обездвижен',[e['name'] for e in self.b.runtime['effects']])
        self.assertFalse(Event.objects.filter(actor=self.alice).latest('id').inputs['mystic_arrows']['hit'])
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['mystic_arrows'],1);self.assertEqual(computed(self.a)['hit'],0)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db()
        self.assertEqual(computed(self.a)['hit'],-1)
        self.turn(scene,self.alice);self.turn(scene,self.bob)
        self.post(self.alice,{**p,'targets':[],'mystic_arrows':['shift']});self.a.refresh_from_db()
        self.assertEqual(computed(self.a)['hit'],-2)
        rows=serialize_char(self.a,self.alice)['abilities']
        self.assertEqual(next(a for a in rows if a['id']==self.bless.id)['hit_bonus'],-2)
        self.assertTrue(Event.objects.filter(actor=self.alice).latest('id').inputs['mystic_arrows']['external_target'])

    def test_double_arrow_target_durations_and_end_battle(self):
        scene,p,_,_=self.mystic_setup(double=True)
        self.post(self.alice,{**p,'mystic_arrows':['frost','bind']})
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['mystic_arrows'],1);self.assertEqual(computed(self.a)['hit'],0)
        self.assertEqual(computed(self.b)['speed'],0)
        self.turn(scene,self.alice);self.turn(scene,self.bob);self.b.refresh_from_db()
        self.assertEqual(computed(self.b)['speed'],3)
        self.assertEqual(self.b.runtime['effects'][0]['remaining'],2)
        for _ in range(2):self.turn(scene,self.alice);self.turn(scene,self.bob)
        self.b.refresh_from_db();self.assertEqual(computed(self.b)['speed'],6)
        self.post(self.alice,{**p,'mystic_arrows':['stun','vulnerable']});self.b.refresh_from_db()
        self.assertEqual({e['name']:e['value'] for e in self.b.runtime['effects']},{'Оглушение':2,'Уязвимость':1})
        scene.refresh_from_db();self.post(self.gm,{'op':'scene.end','scene':scene.id,'version':scene.state})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['mystic_arrows'],0);self.assertEqual(computed(self.a)['hit'],0)
        self.post(self.gm,{'op':'undo'});self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['mystic_arrows'],2);self.assertEqual(computed(self.a)['hit'],-1)
        self.assertEqual(len(self.b.runtime['effects']),2)

    def test_arrow_reaction_is_chosen_by_attacker_and_atomic(self):
        scene,p,_,_=self.mystic_setup()
        self.b.runtime['effects']=[{'key':'bless','status':'Благословение','name':'Благословение','value':2,'stat':'hit','duration':'turns','remaining':3}];self.b.save()
        self.post(self.alice,p,400)
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],1);self.assertEqual(self.a.runtime['mystic_arrows'],0)
        self.assertEqual(self.b.runtime['effects'][0]['name'],'Благословение')
        self.post(self.alice,{**p,'reactions':{str(self.b.id)+':arrow:frost':'bless'}})
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['name'],'Чистые льды')
        self.assertEqual(self.b.runtime['effects'][0]['value'],5)
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['effects'][0]['name'],'Благословение')

    def test_shift_is_instant_and_respects_equipment(self):
        scene,p,_,_=self.mystic_setup()
        earth=self.charm('Малое зачарование земли')
        Item.objects.create(character=self.b,name='Броня земли',equipped=True,data={'item_type':'armor','enchantments':[earth.id]})
        self.post(self.alice,{**p,'mystic_arrows':['shift']});self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['effects'],[]);self.assertEqual(self.b.runtime['hp'],10)
        event=Event.objects.filter(actor=self.alice).latest('id')
        self.assertEqual(event.inputs['mystic_arrows']['movements'],[{'target':self.b.name,'cells':4}])


    def test_stun_strength_is_spent_by_actions_and_carries_to_next_turn(self):
        from .statuses import apply_status
        scene=self.start()
        apply_status(self.b,{'name':'Оглушение','stat':'status','value':3,'duration':'turns','remaining':1})
        apply_status(self.b,{'name':'Оглушение','stat':'status','value':2,'duration':'turns','remaining':1})
        self.b.save();self.turn(scene,self.alice);self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['stun_pending'],3)
        self.assertEqual(self.b.runtime['effects'][0]['duration'],'actions')
        self.assertEqual(self.b.runtime['effects'][0]['value'],5)
        self.post(self.bob,{'op':'action.spend','character':self.b.id,'action':'move'})
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['value'],4)
        self.turn(scene,self.bob);self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['effects'][0]['value'],2)
        self.assertEqual(Event.objects.filter(actor=self.bob).latest('id').inputs['stun_skipped'],2)
        self.post(self.bob,{'op':'undo'});self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['effects'][0]['value'],4)
        self.assertEqual(self.b.runtime['stun_pending'],2)
        self.post(self.bob,{'op':'redo'});self.turn(scene,self.alice)
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['stun_pending'],2)
        self.turn(scene,self.bob);self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['effects'],[])
        self.assertEqual(self.b.runtime['stun_pending'],0)


    def test_stunning_arrow_includes_boulder_damage_only_on_hit(self):
        from .views import serialize_char
        scene,p,_,_=self.mystic_setup()
        boulder=Entry.objects.create(kind='ability',name='Глыба',data={'category':'passive'})
        self.a.abilities.add(boulder)
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==p['ability'])
        stun=next(o for o in row['mystic_arrows']['options'] if o['id']=='stun')
        self.assertEqual(stun['damage_contribution']['value'],2)
        self.post(self.alice,{**p,'mystic_arrows':['stun']})
        event=Event.objects.filter(actor=self.alice).latest('id')
        self.assertEqual(event.inputs['damage_contributions'],[{'key':'boulder_stun','value':2,'type':'Земля','name':'Глыба · Оглушение','once_per_turn':False}])
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['hp'],10)
        self.post(self.alice,{'op':'undo'})
        self.post(self.alice,{**p,'mystic_arrows':['stun'],'outcome':'miss'})
        event=Event.objects.filter(actor=self.alice).latest('id')
        self.assertFalse(event.inputs.get('damage_contributions'))
        boulder.archived=True;boulder.save()
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==p['ability'])
        self.assertNotIn('damage_contribution',next(o for o in row['mystic_arrows']['options'] if o['id']=='stun'))


    def test_repeated_freezing_reaction_adds_unspent_stun_strength(self):
        from .statuses import apply_status
        for _ in range(2):
            apply_status(self.b,{'name':'Влага','status':'Влага','key':'status:Влага','stat':'status','value':1,'duration':'turns','remaining':3})
            apply_status(self.b,{'name':'Мороз','status':'Мороз','stat':'speed','value':-2,'duration':'turns','remaining':3},'status:Влага')
        self.assertEqual(len(self.b.runtime['effects']),1)
        freeze=self.b.runtime['effects'][0]
        self.assertEqual((freeze['status'],freeze['value'],freeze['duration']),('Заморозка',6,'actions'))

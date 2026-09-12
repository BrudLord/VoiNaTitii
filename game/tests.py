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


    def transfer_setup(self):
        scene,p,_,_=self.mystic_setup()
        self.a.refresh_from_db();self.a.level=8
        self.a.runtime['mystic_arrows']=3
        self.a.runtime['effects']=[{'key':'status:Истощение маны','status':'Истощение маны','name':'Истощение маны','stat':'hit','value':-2,'duration':'battle'}]
        self.a.save()
        ability=Entry.objects.create(kind='ability',name='Передача истощения',data={'category':'active','action':'minor','circle':2})
        self.a.abilities.add(ability)
        prepare={'op':'ability.use','character':self.a.id,'ability':ability.id,'targets':[]}
        return scene,p,prepare

    def test_transfer_snapshots_strength_survives_miss_and_supports_undo(self):
        scene,p,prepare=self.transfer_setup()
        self.post(self.alice,prepare);self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.assertEqual(self.a.runtime['used'][str(prepare['ability'])],1)
        self.post(self.alice,{**p,'outcome':'miss','mystic_arrows':['shift']});self.a.refresh_from_db()
        self.assertEqual(computed(self.a)['hit'],-3)
        self.assertEqual(self.a.runtime['exhaustion_transfer']['strength'],2)
        self.turn(scene,self.alice);self.turn(scene,self.bob)
        self.post(self.alice,{**p,'mystic_arrows':['shift']});self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(computed(self.a)['hit'],-4);self.assertEqual(computed(self.b)['hit'],-2)
        self.assertNotIn('exhaustion_transfer',self.a.runtime)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['exhaustion_transfer']['strength'],2);self.assertEqual(computed(self.b)['hit'],0)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertNotIn('exhaustion_transfer',self.a.runtime);self.assertEqual(computed(self.b)['hit'],-2)

    def test_transfer_selects_one_target_and_adds_to_existing_exhaustion(self):
        scene,p,prepare=self.transfer_setup();self.post(self.alice,prepare)
        attack=Entry.objects.create(kind='ability',name='Атака по площади',data={'category':'active','damage':True,'formula':'1к6','action':'main'})
        self.a.abilities.add(attack)
        q={'op':'ability.use','character':self.a.id,'ability':attack.id,'targets':[self.a.id,self.b.id],'roll_result':'4'}
        self.post(self.alice,q,400);self.post(self.alice,{**q,'exhaustion_target':9999},400)
        self.post(self.bob,{**q,'exhaustion_target':self.b.id},403)
        self.b.runtime['effects']=[{'key':'status:Истощение маны','status':'Истощение маны','stat':'hit','value':-1,'duration':'battle'}];self.b.save()
        self.post(self.alice,{**q,'exhaustion_target':self.b.id});self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(computed(self.a)['hit'],-2);self.assertEqual(computed(self.b)['hit'],-3)
        self.assertEqual(self.b.runtime['hp'],10)
        self.post(self.alice,{'op':'undo'})
        self.post(self.alice,{**q,'exhaustion_target':0});self.b.refresh_from_db()
        self.assertEqual(computed(self.b)['hit'],-1)
        self.assertEqual(Event.objects.filter(actor=self.alice).latest('id').inputs['exhaustion_transfer']['target'],'Цель на игровом поле')

    def test_transfer_requires_exhaustion_and_is_cleared_at_battle_end(self):
        from .views import serialize_char
        scene,p,prepare=self.transfer_setup()
        self.post(self.alice,{**prepare,'targets':[self.b.id]},400)
        self.a.runtime['effects']=[];self.a.save()
        self.post(self.alice,prepare,400)
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==prepare['ability'])
        self.assertEqual(row['reason'],'Нет истощения маны для передачи')
        self.a.runtime['effects']=[{'key':'status:Истощение маны','status':'Истощение маны','stat':'hit','value':-2,'duration':'battle'}];self.a.save()
        self.post(self.alice,prepare)
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':self.bless.id,'targets':[self.b.id]})
        self.a.refresh_from_db();self.assertIn('exhaustion_transfer',self.a.runtime)
        scene.refresh_from_db();self.post(self.gm,{'op':'scene.end','scene':scene.id,'version':scene.state})
        self.a.refresh_from_db();self.assertNotIn('exhaustion_transfer',self.a.runtime)
        self.post(self.gm,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['exhaustion_transfer']['strength'],2)


    def test_transfer_can_be_prepared_with_a_held_minor_action(self):
        scene,p,prepare=self.transfer_setup()
        self.post(self.alice,{'op':'action.spend','character':self.a.id,'action':'main','exchange':'minor'})
        self.post(self.alice,{'op':'action.ready','character':self.a.id,'action':'minor','condition':'Союзник подаст знак'})
        self.turn(scene,self.alice)
        self.post(self.alice,{**prepare,'use_ready':True,'triggered':True,'dex_roll':12})
        self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['exhaustion_transfer']['strength'],2)
        self.assertNotIn('readied',self.a.runtime)
        self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertNotIn('exhaustion_transfer',self.a.runtime)
        self.assertIn('readied',self.a.runtime)


    def test_single_attack_cannot_transfer_to_a_different_external_target(self):
        scene,p,prepare=self.transfer_setup();self.post(self.alice,prepare)
        self.post(self.alice,{**p,'mystic_arrows':['shift'],'exhaustion_target':0},400)
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['main'],1)
        self.assertEqual(self.a.runtime['exhaustion_transfer']['strength'],2)
        self.post(self.alice,{**p,'targets':[],'mystic_arrows':['shift'],'exhaustion_target':0})
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertNotIn('exhaustion_transfer',self.a.runtime)
        self.assertEqual(computed(self.b)['hit'],0)

    def seeking_setup(self):
        scene,p,bow,_=self.mystic_setup()
        seeking=Entry.objects.create(kind='ability',name='Ищущие стрелы',data={'circle':2,'action':'minor','manual':True})
        self.a.level=8;self.a.save();self.a.abilities.add(seeking)
        return scene,p,bow,seeking

    def test_seeking_repeat_uses_minor_and_mystic_effects_with_undo(self):
        from .views import serialize_char
        scene,p,_,seeking=self.seeking_setup()
        repeat={**p,'ability':seeking.id,'targets':[self.a.id]}
        self.post(self.alice,repeat,400)
        self.post(self.alice,{**p,'outcome':'miss'})
        self.a.refresh_from_db()
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==seeking.id)
        self.assertEqual(row['reason'],'');self.assertTrue(row['rolls_required'])
        self.assertTrue(row['mystic_arrows']);self.assertIn('1к6',row['formula'])
        self.assertEqual(row['data']['action'],'minor');self.assertFalse(row['data']['manual'])
        self.post(self.alice,{**repeat,'targets':[self.b.id]},400)
        self.post(self.alice,{**repeat,'roll_result':''},400)
        self.post(self.bob,repeat,403)
        self.post(self.alice,repeat)
        self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],0)
        self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.assertEqual(self.a.runtime['used'][str(seeking.id)],1)
        self.assertEqual(self.a.runtime['mystic_arrows'],2)
        self.assertNotIn('missed_standard',self.a.runtime)
        self.assertTrue(any(e.get('status')=='Мороз' for e in self.a.runtime['effects']))
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['minor'],1)
        self.assertEqual(self.a.runtime['missed_standard']['targets'],[self.b.id])
        self.assertEqual(self.a.runtime['mystic_arrows'],1)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db()
        self.assertNotIn('missed_standard',self.a.runtime)

    def test_seeking_external_target_and_weapon_and_turn_validation(self):
        scene,p,bow,seeking=self.seeking_setup()
        self.post(self.alice,{**p,'targets':[],'outcome':'miss'})
        repeat={**p,'ability':seeking.id,'targets':[]}
        self.post(self.alice,repeat,400)
        self.post(self.alice,{**repeat,'different_target':'yes'},400)
        self.a.refresh_from_db();self.a.runtime['weapon_id']=0;self.a.save()
        self.post(self.alice,{**repeat,'different_target':True},400)
        self.a.runtime['weapon_id']=bow.id;self.a.save()
        self.post(self.alice,{**repeat,'different_target':True,'outcome':'miss'})
        self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['missed_standard']['targets'],[])
        self.turn(scene,self.alice);self.turn(scene,self.bob)
        self.post(self.alice,{**repeat,'different_target':True},400)
        scene.refresh_from_db()
        self.post(self.gm,{'op':'scene.end','scene':scene.id,'version':scene.state})
        self.a.refresh_from_db();self.assertNotIn('missed_standard',self.a.runtime)

    def test_seeking_cannot_use_an_unlearned_or_archived_ability(self):
        scene,p,_,seeking=self.seeking_setup()
        self.post(self.alice,{**p,'outcome':'miss'})
        repeat={**p,'ability':seeking.id,'targets':[]}
        self.a.abilities.remove(seeking);self.post(self.alice,repeat,403)
        self.a.abilities.add(seeking);seeking.archived=True;seeking.save()
        self.post(self.alice,repeat,404)

    def test_another_attack_replaces_the_miss_that_seeking_can_repeat(self):
        scene,p,_,seeking=self.seeking_setup()
        self.post(self.alice,{**p,'outcome':'miss'})
        self.a.refresh_from_db();self.a.runtime['actions']['main']=1;self.a.save()
        other=Entry.objects.create(kind='ability',name='Другая атака',data={'damage':True,'circle':0,'action':'main'})
        self.a.abilities.add(other)
        self.post(self.alice,{**p,'ability':other.id,'mystic_arrows':[],'outcome':'miss'})
        self.post(self.alice,{**p,'ability':seeking.id,'targets':[]},400)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['missed_standard']['targets'],[self.b.id])
        self.post(self.alice,{**p,'ability':seeking.id,'targets':[]})

    def charged_setup(self):
        scene,p,_,_=self.mystic_setup()
        prepare=Entry.objects.create(kind='ability',name='Заряженные стрелы',data={'circle':3,'action':'minor','rolls':True})
        attack=Entry.objects.create(kind='ability',name='Двойной выстрел для проверки',data={'circle':1,'action':'main','weapon':True,'damage':True,'formula':'2Ор + Мод'})
        self.a.refresh_from_db();self.a.level=8;self.a.save();self.a.abilities.add(prepare,attack)
        prep={'op':'ability.use','character':self.a.id,'ability':prepare.id,'targets':[]}
        shot={**p,'ability':attack.id,'mystic_arrows':[],'charged_arrows':['stun','stun']}
        return scene,prep,shot

    def test_charged_arrows_repeat_effects_and_undo_without_mana_cost(self):
        from .views import serialize_char
        scene,prep,shot=self.charged_setup()
        self.post(self.alice,shot,400)
        self.post(self.alice,prep)
        self.a.refresh_from_db()
        ability=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==shot['ability'])
        self.assertEqual(ability['charged_arrows']['limit'],2)
        self.post(self.alice,{**shot,'outcome':'critical'})
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertNotIn('charged_arrows',self.a.runtime)
        self.assertEqual(self.a.runtime['mystic_arrows'],0)
        self.assertFalse(any(e.get('status')=='Истощение маны' for e in self.a.runtime['effects']))
        stun=next(e for e in self.b.runtime['effects'] if e.get('status')=='Оглушение')
        self.assertEqual(stun['value'],4)
        self.assertEqual(self.b.runtime['hp'],10)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertIn('charged_arrows',self.a.runtime);self.assertEqual(self.b.runtime['effects'],[])
        self.assertEqual(self.a.runtime['actions']['main'],1)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db()
        self.assertNotIn('charged_arrows',self.a.runtime)

    def test_charged_arrows_reject_extra_slots_and_invalid_targets_atomically(self):
        scene,prep,shot=self.charged_setup();self.post(self.alice,prep)
        for extra in [{'charged_arrows':['frost']*3},{'charged_arrows':['unknown']},{'charged_arrows':'frost'},
                      {'charged_target':self.a.id},{'targets':[self.a.id,self.b.id]}, {'roll_result':''}]:
            self.post(self.alice,{**shot,**extra},400)
        self.post(self.bob,shot,403)
        self.a.refresh_from_db();self.assertIn('charged_arrows',self.a.runtime)
        self.assertEqual(self.a.runtime['actions']['main'],1)
        self.post(self.alice,{**shot,'targets':[self.a.id,self.b.id],'charged_target':self.b.id})
        self.a.refresh_from_db();self.assertFalse(any(e.get('status')=='Оглушение' for e in self.a.runtime['effects']))

    def test_charged_arrows_survive_circle_zero_but_are_spent_on_a_miss(self):
        scene,prep,shot=self.charged_setup();self.post(self.alice,prep)
        standard=Entry.objects.get(name='Стандартная атака')
        self.post(self.alice,{**shot,'ability':standard.id,'charged_arrows':[],'mystic_arrows':['shift'],'outcome':'miss'})
        self.a.refresh_from_db();self.assertIn('charged_arrows',self.a.runtime)
        self.turn(scene,self.alice);self.turn(scene,self.bob)
        self.post(self.alice,{**shot,'outcome':'miss'})
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertNotIn('charged_arrows',self.a.runtime);self.assertEqual(self.b.runtime['effects'],[])
        self.assertEqual(self.a.runtime['mystic_arrows'],1)

    def test_charged_arrows_are_spent_by_non_weapon_circle_one_and_reset_at_end(self):
        scene,prep,shot=self.charged_setup();self.post(self.alice,prep)
        heal=Entry.objects.create(kind='ability',name='Фиксированное лечение',data={'circle':1,'effects':[{'stat':'hp','value':3}]})
        self.a.abilities.add(heal)
        self.post(self.alice,{**shot,'ability':heal.id,'charged_arrows':[]})
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertNotIn('charged_arrows',self.a.runtime);self.assertEqual(self.b.runtime['hp'],13)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertIn('charged_arrows',self.a.runtime)
        scene.refresh_from_db();self.post(self.gm,{'op':'scene.end','scene':scene.id,'version':scene.state})
        self.a.refresh_from_db();self.assertNotIn('charged_arrows',self.a.runtime)
        self.post(self.gm,{'op':'undo'});self.a.refresh_from_db();self.assertIn('charged_arrows',self.a.runtime)

    def test_charged_arrows_external_target_and_boulder_contributions(self):
        scene,prep,shot=self.charged_setup()
        self.a.abilities.add(Entry.objects.create(kind='ability',name='Глыба',data={'category':'passive'}))
        self.post(self.alice,prep)
        self.post(self.alice,{**shot,'targets':[],'outcome':'critical'})
        event=Event.objects.latest('id')
        parts=event.inputs['damage_contributions']
        self.assertEqual(sum(p['value'] for p in parts if p['key']=='boulder_stun'),4)
        self.assertTrue(event.inputs['charged_arrows']['external_target'])

    def test_charged_single_target_and_reaction_validation(self):
        scene,prep,shot=self.charged_setup()
        attack=Entry.objects.get(pk=shot['ability']);attack.data['target']='single';attack.save()
        self.post(self.alice,prep)
        self.post(self.alice,{**shot,'charged_target':0},400)
        self.b.refresh_from_db();self.b.runtime['effects']=[{'key':'bless','status':'Благословение','name':'Благословение','stat':'hit','value':2,'duration':'turns','remaining':3}];self.b.save()
        frost={**shot,'charged_arrows':['frost']}
        key=f'{self.b.id}:arrow:charged:0:frost'
        self.post(self.alice,{**frost,'reactions':{key:'unknown'}},400)
        self.a.refresh_from_db();self.assertIn('charged_arrows',self.a.runtime)
        self.post(self.alice,{**frost,'reactions':{key:'bless'}})
        self.b.refresh_from_db()
        self.assertTrue(any(e.get('status')=='Чистые льды' for e in self.b.runtime['effects']))

    def book_row(self,name):
        from pathlib import Path
        from .book_audit import abilities
        return next((desc,data,source) for n,desc,data,source in abilities(Path('rules/player-book.txt').read_text()) if n==name)

    def test_book_literal_effects_use_local_durations_and_recipient_scope(self):
        for name in ['Отравленный дротик','Ослабление']:
            _,data,_=self.book_row(name)
            self.assertEqual(data['effects'][0]['turns'],1)
        _,data,_=self.book_row('Слепота')
        self.assertEqual(data['target'],'multiple')
        self.assertEqual({e['name']:e['turns'] for e in data['effects']},{'Проклятье':3,'Ослепление':1})
        _,data,_=self.book_row('Благословение')
        self.assertTrue(any(e['stat']=='temp' and e['value']==5 for e in data['effects']))
        self.assertTrue(any(e['stat']=='damage' and e['value']==1 and e['duration']=='battle' for e in data['effects']))
        self.assertTrue(any(e['stat']=='hit' and e['turns']==3 for e in data['effects']))
        for name in ['Болотная тень','Атака тотема','Огненная стена']:
            _,data,_=self.book_row(name);self.assertNotIn('effects',data)
        _,data,_=self.book_row('Кислотный выброс')
        self.assertEqual([e['name'] for e in data['effects']],['Оглушение'])
        self.assertEqual(data['effects'][0]['duration'],'actions')
        _,data,_=self.book_row('Жидкое пламя')
        self.assertEqual(data['formula'],'1к8');self.assertTrue(data['damage'])
        self.assertEqual(data['target'],'multiple')

    def test_imported_one_turn_slow_expires_on_target_turn_and_can_be_undone(self):
        desc,data,source=self.book_row('Отравленный дротик')
        ability=Entry.objects.create(kind='ability',name='Отравленный дротик',description=desc,data=data,source=source)
        self.a.abilities.add(ability);self.a.level=8;self.a.save()
        scene=self.start()
        before=computed(self.b)['speed']
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':ability.id,'targets':[self.b.id],'outcome':'hit','roll_result':'Попадание 16, урон 5'})
        self.b.refresh_from_db();self.assertEqual(computed(self.b)['speed'],before-2)
        self.turn(scene,self.alice);self.b.refresh_from_db();self.assertEqual(computed(self.b)['speed'],before-2)
        self.turn(scene,self.bob);self.b.refresh_from_db();self.assertEqual(computed(self.b)['speed'],before)
        self.post(self.bob,{'op':'undo'});self.b.refresh_from_db();self.assertEqual(computed(self.b)['speed'],before-2)

    def test_imported_area_effect_applies_to_multiple_selected_targets(self):
        desc,data,source=self.book_row('Лунный свет')
        ability=Entry.objects.create(kind='ability',name='Лунный свет',description=desc,data=data,source=source)
        self.a.abilities.add(ability);self.a.level=8;self.a.save();self.start()
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':ability.id,'targets':[self.a.id,self.b.id],'roll_result':'Броски попадания 15 и 16, урон 5'})
        for c in [self.a,self.b]:
            c.refresh_from_db();self.assertTrue(any(e['name']=='Ослабление' and e['value']==-2 for e in c.runtime['effects']))
        self.post(self.alice,{'op':'undo'})
        for c in [self.a,self.b]:c.refresh_from_db();self.assertEqual(c.runtime['effects'],[])

    def test_reimport_removes_old_wrong_effects_and_preserves_master_edits(self):
        from django.core.management import call_command
        from io import StringIO
        for name in ['Болотная тень','Атака тотема']:
            desc,data,source=self.book_row(name)
            Entry.objects.create(kind='ability',name=name,description=desc,source=source,data={**data,'book_compiled':1,'target':'single','effects':[{'stat':'status','value':99}]})
        desc,data,source=self.book_row('Отравленный дротик')
        edited=Entry.objects.create(kind='ability',name='Отравленный дротик',source=source,data=data)
        custom={**data,'effects':[{'stat':'speed','value':-7,'turns':2}]}
        self.post(self.gm,{'op':'entry.save','id':edited.id,'kind':'ability','name':edited.name,'description':'Правка мастера','data':custom})
        call_command('audit_book',stdout=StringIO())
        for name in ['Болотная тень','Атака тотема']:
            row=Entry.objects.get(kind='ability',name=name)
            self.assertNotIn('effects',row.data);self.assertNotIn('target',row.data)
        edited.refresh_from_db();self.assertEqual(edited.description,'Правка мастера')
        self.assertEqual(edited.data['effects'],custom['effects']);self.assertTrue(edited.data['reviewed'])

    def test_end_of_current_turn_is_distinct_from_one_target_turn(self):
        desc,data,source=self.book_row('Свет')
        # This literal ally bonus expires with the acting character's turn.
        self.assertEqual(data['effects'][0]['duration'],'current_turn')
        ability=Entry.objects.create(kind='ability',name='Свет',description=desc,data=data,source=source)
        self.a.abilities.add(ability);self.a.level=8;self.a.save();scene=self.start()
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':ability.id,'targets':[self.b.id]})
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['value'],2)
        self.turn(scene,self.alice);self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['value'],2)

    def test_literal_import_does_not_truncate_variable_strength_or_merge_recipient_groups(self):
        from .book_effects import literal_effects
        for desc in ['Цель получает Продолжительный урон 2\\*Мод.', 'Цель получает Кровотечение 2к4.',
                     'Цель получает Метка Порчи на 3 хода.']:
            self.assertEqual(literal_effects(desc)[0],[])
        effects,target=literal_effects('Цель получает Оглушение 2. Цели вокруг получают Мороз 3.')
        self.assertEqual([e['name'] for e in effects],['Оглушение']);self.assertEqual(target,'single')
        effects,_=literal_effects('Цель получает -2 КД на 1 ход.')
        self.assertEqual(effects[0]['stat'],'ac');self.assertEqual(effects[0]['turns'],1)

    def test_damage_without_the_word_damage_and_escaped_modifier_multiplier(self):
        _,data,_=self.book_row('Каменные шипы')
        self.assertEqual(data['formula'],'2к6+Мод');self.assertTrue(data['damage'])
        _,data,_=self.book_row('Морозное касание')
        self.assertEqual(data['formula'],'1к6+2*Мод');self.assertTrue(data['damage'])

    def test_modifier_multipliers_are_calculated_without_critical_multiplication(self):
        desc,data,source=self.book_row('Струя пламени')
        data['stat']='cha'
        ability=Entry.objects.create(kind='ability',name='Струя пламени',description=desc,data=data)
        self.assertEqual(formula(self.a,ability),'1к6+6')
        self.assertEqual(formula(self.a,ability,True),'2к6+6')
        self.a.stats['cha']=8
        self.assertEqual(formula(self.a,ability),'1к6-2')

    def test_imported_attack_can_target_external_enemy_and_logs_effects_without_touching_allies(self):
        desc,data,source=self.book_row('Отравленный дротик')
        ability=Entry.objects.create(kind='ability',name='Отравленный дротик',description=desc,data=data)
        self.a.abilities.add(ability);self.a.level=8;self.a.save();self.start()
        payload={'op':'ability.use','character':self.a.id,'ability':ability.id,'targets':[],'roll_result':'Попадание 15, урон 4'}
        self.post(self.alice,payload)
        event=Event.objects.latest('id');self.assertEqual(event.inputs['external_effects'],data['effects'])
        for c in [self.a,self.b]:c.refresh_from_db();self.assertEqual(c.runtime['effects'],[]);self.assertEqual(c.runtime['hp'],10)
        self.post(self.alice,{'op':'undo'})
        self.post(self.alice,{**payload,'outcome':'miss'})
        self.assertNotIn('external_effects',Event.objects.latest('id').inputs)
        self.post(self.alice,{'op':'undo'})
        heal=Entry.objects.create(kind='ability',name='Лечение',data={'effects':[{'stat':'hp','value':5}]})
        self.a.abilities.add(heal)
        self.post(self.alice,{**payload,'ability':heal.id},400)

    def bp_setup(self):
        desc,data,source=self.book_row('Фокусирующий удар')
        grant=Entry.objects.create(kind='ability',name='Фокусирующий удар',description=desc,data=data)
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'damage':True,'formula':'1Ор + Мод'})
        Item.objects.create(character=self.a,name='Меч для БП',equipped=True,data={'item_type':'weapon','dice':'1к6','no_proficiency':True})
        self.a.abilities.add(grant);self.a.level=8;self.a.save();scene=self.start()
        payload={'op':'ability.use','character':self.a.id,'ability':grant.id,'targets':[self.b.id],'roll_result':'Попадание 15, урон 4'}
        return scene,attack,payload

    def test_bp_is_applied_after_attack_and_only_affects_attacks_against_its_target(self):
        from .views import serialize_char
        scene,attack,p=self.bp_setup();self.post(self.alice,p)
        self.assertEqual(Event.objects.latest('id').inputs['attack_targets'][0]['target_bonus'],0)
        self.b.refresh_from_db();bp=next(e for e in self.b.runtime['effects'] if e['name']=='БП')
        self.assertEqual((bp['value'],bp['remaining']),(2,1))
        self.assertEqual(computed(self.b)['hit'],0)
        self.a.refresh_from_db();self.a.runtime['actions']['main']=1;self.a.save()
        base=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==attack.id)['hit_bonus']
        self.post(self.alice,{**p,'ability':attack.id,'targets':[self.a.id,self.b.id]})
        rows=Event.objects.latest('id').inputs['attack_targets']
        self.assertEqual([r['hit'] for r in rows],[base,base+2])
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db()
        self.assertTrue(any(e['name']=='БП' for e in self.b.runtime['effects']))

    def test_bp_expires_at_end_of_target_turn_and_turn_undo_restores_it(self):
        scene,attack,p=self.bp_setup();self.post(self.alice,p)
        self.turn(scene,self.alice);self.b.refresh_from_db()
        self.assertTrue(any(e['name']=='БП' for e in self.b.runtime['effects']))
        self.turn(scene,self.bob);self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])
        self.post(self.bob,{'op':'undo'});self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['value'],2)

    def test_external_bp_is_validated_and_cannot_override_tracked_targets(self):
        scene,attack,p=self.bp_setup()
        payload={**p,'ability':attack.id,'targets':[],'external_bp':3}
        for value in [-1,1001,1.5,'3',True]:self.post(self.alice,{**payload,'external_bp':value},400)
        self.post(self.alice,{**payload,'targets':[self.b.id]},400)
        self.post(self.alice,payload)
        row=Event.objects.latest('id').inputs['attack_targets'][0]
        self.assertEqual(row['target_bonus'],3);self.assertIsNone(row['id'])
        for c in [self.a,self.b]:c.refresh_from_db();self.assertEqual(c.runtime['effects'],[])

    def test_target_bonuses_respect_ability_keywords_and_bp_does_not_stack(self):
        from .targeting import resolve
        from .statuses import apply_status
        scene,attack,p=self.bp_setup()
        self.b.runtime['effects']=[]
        apply_status(self.b,{'name':'БП','stat':'target_hit','value':3,'duration':'turns','remaining':1})
        apply_status(self.b,{'name':'БП','stat':'target_hit','value':2,'duration':'turns','remaining':3})
        self.assertEqual((self.b.runtime['effects'][0]['value'],self.b.runtime['effects'][0]['remaining']),(3,3))
        self.b.runtime['effects'].append({'key':'fire','name':'Уязвимое пламя','stat':'target_hit','value':4,'keyword':'Огонь'})
        self.assertEqual(resolve(self.a,attack,computed(self.a),[self.b],{})[0]['target_bonus'],3)
        attack.data['keywords']=['Огонь']
        self.assertEqual(resolve(self.a,attack,computed(self.a),[self.b],{})[0]['target_bonus'],7)

    def test_master_can_edit_bp_effect_and_cast_miss_does_not_apply_it(self):
        scene,attack,p=self.bp_setup()
        self.post(self.gm,{'op':'effect.apply','character':self.b.id,'name':'БП','value':2,'turns':1})
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['stat'],'target_hit')
        self.post(self.gm,{'op':'undo'})
        self.post(self.alice,{**p,'outcome':'miss'})
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])

    def test_used_target_bonus_cannot_be_undone_until_dependent_attack_is_undone(self):
        scene,attack,p=self.bp_setup()
        self.post(self.gm,{'op':'effect.apply','character':self.b.id,'name':'БП','value':2,'turns':1})
        self.post(self.alice,{**p,'ability':attack.id})
        self.post(self.gm,{'op':'undo'},400)
        self.post(self.alice,{'op':'undo'})
        self.post(self.gm,{'op':'undo'})
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])

    def test_literal_attack_hit_bonuses_are_scoped_to_the_named_ability(self):
        from .views import serialize_char
        expected={'Молот света':2,'Точный выстрел':3,'Неожиданный удар':1,'Точный бросок':3,'Обманный удар':4}
        for name,value in expected.items():
            desc,data,source=self.book_row(name)
            self.assertEqual(data['attack_hit_bonus'],value)
            ability=Entry.objects.create(kind='ability',name=name,description=desc,data=data)
            self.a.abilities.add(ability)
            row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==ability.id)
            self.assertEqual(row['hit_bonus'],value)
        self.assertEqual(computed(self.a)['hit'],0)
        _,hammer,_=self.book_row('Молот света')
        self.assertTrue(any(e['name']=='БП' and e['duration']=='battle' for e in hammer['effects']))

    def test_numerical_superiority_uses_bp_only_and_does_not_double_it_on_critical(self):
        from .targeting import resolve
        desc,data,source=self.book_row('Численное превосходство')
        ability=Entry.objects.create(kind='ability',name='Численное превосходство',description=desc,data=data)
        self.a.abilities.add(ability)
        Item.objects.create(character=self.a,name='Цепь',equipped=True,data={'item_type':'weapon','dice':'1к6','families':data.get('requires',[]),'no_proficiency':True})
        self.b.runtime['effects']=[{'key':'status:БП','name':'БП','stat':'target_hit','value':2,'duration':'turns','remaining':3},
                                   {'key':'other','name':'Иной бонус','stat':'target_hit','value':4,'duration':'battle'}]
        self.b.save();scene=self.start()
        before=formula(self.a,ability,True)
        p={'op':'ability.use','character':self.a.id,'ability':ability.id,'targets':[self.b.id],'outcome':'critical','roll_result':'Крит, урон 8'}
        self.post(self.alice,p)
        row=Event.objects.latest('id').inputs['attack_targets'][0]
        self.assertEqual(row['bp_damage'],2);self.assertEqual(row['target_bonus'],6)
        self.assertEqual(row['damage'],before+' +2 [БП]')
        self.assertEqual(row['hit'],6)
        self.post(self.alice,{'op':'undo'})
        self.post(self.alice,{**p,'targets':[],'external_bp':3})
        row=Event.objects.latest('id').inputs['attack_targets'][0]
        self.assertEqual(row['damage'],before+' +3 [БП]')
        self.assertEqual(row['bp_damage'],3)

    def test_target_damage_formula_contains_selected_arrow_contributions_once(self):
        scene,prep,shot=self.charged_setup()
        self.a.abilities.add(Entry.objects.create(kind='ability',name='Глыба',data={'category':'passive'}))
        self.post(self.alice,prep)
        self.post(self.alice,{**shot,'outcome':'critical'})
        row=Event.objects.latest('id').inputs['attack_targets'][0]
        self.assertIn('4к6',row['damage'])
        self.assertEqual(row['damage'].count('+2 [Земля]'),2)

    def test_target_damage_rider_is_not_copied_to_other_targets(self):
        from .targeting import finalize
        from types import SimpleNamespace
        change=SimpleNamespace(inputs={'attack_targets':[{'id':1,'damage':'1к6'},{'id':2,'damage':'1к6'}],
            'charged_arrows':{'hit':True,'target_ids':[2],'choices':[{'damage_contribution':{'value':2,'type':'Земля'}}]}})
        finalize(change)
        self.assertEqual([r['damage'] for r in change.inputs['attack_targets']],['1к6','1к6 +2 [Земля]'])

    def test_master_attack_bonus_parameters_are_validated(self):
        for data in [{'attack_hit_bonus':'3'},{'attack_hit_bonus':1001},{'damage_from_bp':'yes'}]:
            self.post(self.gm,{'op':'entry.save','kind':'ability','name':'Проверка бонуса','data':data},400)
        self.post(self.gm,{'op':'entry.save','kind':'ability','name':'Проверка бонуса','data':{'attack_hit_bonus':-2,'damage_from_bp':True}})
        data=Entry.objects.get(name='Проверка бонуса').data
        self.assertEqual(data['attack_hit_bonus'],-2);self.assertTrue(data['damage_from_bp'])

    def test_weapon_family_requirement_uses_selected_weapon_without_duplicate_keywords(self):
        from .rules import availability
        scene=self.start()
        chain=Item.objects.create(character=self.a,name='Цепь',equipped=True,data={'item_type':'weapon','dice':'1к6','families':['Цепы']})
        bow=Item.objects.create(character=self.a,name='Лук',equipped=True,data={'item_type':'weapon','dice':'1к6','families':['Луки']})
        ability=Entry.objects.create(kind='ability',name='Удар цепью',data={'weapon':True,'requires':['Цепы']})
        self.a.refresh_from_db();self.a.runtime['weapon_id']=chain.id
        self.assertEqual(availability(self.a,ability,scene),'')
        self.a.runtime['weapon_id']=bow.id
        self.assertEqual(availability(self.a,ability,scene),'Нужно подходящее оружие')

    def test_prone_melee_bonus_does_not_change_owner_hit_or_speed(self):
        from .targeting import resolve
        self.b.runtime['effects']=[{'key':'prone','name':'Сбит с ног','stat':'status','value':1,'duration':'battle'}]
        self.b.save()
        calc=computed(self.b)
        self.assertEqual((calc['hit'],calc['speed']),(0,6))
        for word,bonus in [('Ближний 1',2),('Дальнобойный 5',0),('Вспышка 1',0)]:
            ability=Entry(name='Атака',data={'damage':True,'formula':'1к6','keywords':[word]})
            row=resolve(self.a,ability,computed(self.a),[self.b],{})[0]
            self.assertEqual(row['target_bonus'],bonus)

    def test_stand_spends_movement_and_undo_redo_restores_prone(self):
        self.start();self.a.refresh_from_db()
        self.a.runtime['effects']=[{'key':'prone','name':'Сбит с ног','stat':'status','value':1,'duration':'battle'},
                                   {'key':'bless','name':'Благословение','stat':'hit','value':2,'duration':'battle'}]
        self.a.save()
        payload={'op':'action.spend','character':self.a.id,'action':'move','exchange':'stand'}
        self.post(self.bob,payload,403)
        self.post(self.alice,{**payload,'action':'main'},400)
        self.post(self.alice,payload)
        self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['move'],0)
        self.assertEqual([e['name'] for e in self.a.runtime['effects']],['Благословение'])
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['move'],1)
        self.assertEqual(len(self.a.runtime['effects']),2)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['move'],0)
        self.assertEqual(len(self.a.runtime['effects']),1)
        self.post(self.alice,payload,400)

    def test_standing_cannot_bypass_skipped_actions(self):
        self.start();self.a.refresh_from_db()
        self.a.runtime['effects']=[{'key':'prone','name':'Сбит с ног','stat':'status','value':1,'duration':'battle'}]
        self.a.runtime['stun_pending']=1;self.a.save()
        self.post(self.alice,{'op':'action.spend','character':self.a.id,'action':'move','exchange':'stand'},400)
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['move'],1)
        self.assertEqual(len(self.a.runtime['effects']),1)

    def test_prone_book_effects_and_external_bonus(self):
        from .targeting import resolve
        for name in ['Гейзер','Бушующее море']:
            desc,data,source=self.book_row(name)
            effects=[e for e in data.get('effects',[]) if e.get('name')=='Сбит с ног']
            self.assertEqual(len(effects),1,name)
            self.assertEqual(effects[0]['duration'],'battle')
        ability=Entry(name='Атака',data={'damage':True,'formula':'1к6','keywords':['Ближний 1'],'damage_from_bp':True})
        row=resolve(self.a,ability,computed(self.a),[],{'external_bp':3,'external_prone':True})[0]
        self.assertEqual(row['target_bonus'],5)
        self.assertEqual(row['bp_damage'],3)
        ability.data['keywords']=['Дальнобойный 5']
        self.assertEqual(resolve(self.a,ability,computed(self.a),[],{'external_prone':True})[0]['target_bonus'],0)

    def grip_setup(self):
        weapon=Item.objects.create(character=self.a,name='Бастард',equipped=True,data={'item_type':'weapon','dice':'1к6','keywords':['Универсальное (1к10)'],'families':['Мечи'],'no_proficiency':True})
        self.a.runtime['weapon_id']=weapon.id;self.a.save()
        return weapon,{'op':'weapon.grip','character':self.a.id,'item':weapon.id,'grip':'two'}

    def test_versatile_weapon_changes_dice_keywords_and_critical(self):
        from .weaponry import keywords
        weapon,p=self.grip_setup()
        attack=Entry(name='Удар',data={'weapon':True,'formula':'2Ор + Мод','keywords':['Ближний']})
        self.assertEqual(formula(self.a,attack),'2к6 + 3')
        self.post(self.alice,p);self.a.refresh_from_db()
        calc=computed(self.a)
        self.assertEqual(formula(self.a,attack),'2к10 + 3')
        self.assertEqual(formula(self.a,attack,True),'4к10 + 3')
        self.assertIn('Двуручное',calc['keywords']);self.assertNotIn('Одноручное',calc['keywords'])
        self.assertIn('Двуручное',keywords(attack,calc))
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(formula(self.a,attack),'2к6 + 3')
        self.assertIn('Одноручное',computed(self.a)['keywords'])
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db()
        self.assertEqual(formula(self.a,attack),'2к10 + 3')

    def test_grip_in_combat_costs_minor_and_preserves_it_on_rejection(self):
        weapon,p=self.grip_setup();self.start()
        self.post(self.bob,p,403)
        self.post(self.alice,{**p,'grip':'invalid'},400)
        self.post(self.alice,{**p,'item':0},400)
        self.post(self.alice,p)
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.post(self.alice,{**p,'grip':'one'},400)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();weapon.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['minor'],1)
        self.assertEqual(weapon.data.get('grip','one'),'one')
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db();weapon.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.assertEqual(weapon.data['grip'],'two')

    def test_grip_cannot_bypass_turn_or_stun_or_change_other_weapon(self):
        weapon,p=self.grip_setup();scene=self.start();self.a.refresh_from_db()
        self.a.runtime['stun_pending']=1;self.a.save();self.post(self.alice,p,400)
        self.a.runtime['stun_pending']=0;self.a.save()
        self.turn(scene,self.alice);self.post(self.alice,p,400)
        weapon.refresh_from_db();self.assertNotIn('grip',weapon.data)

    def test_two_handed_bonus_uses_effective_weapon_keyword(self):
        from .enchantments import ability_bonus
        weapon,p=self.grip_setup()
        self.a.runtime['effects']=[{'key':'two','name':'Тяжёлый удар','stat':'damage','value':2,'keyword':'Двуручное'}];self.a.save()
        attack=Entry(name='Атака',data={'weapon':True,'keywords':['Ближний']})
        self.assertEqual(ability_bonus(computed(self.a),attack,'damage'),0)
        self.post(self.alice,p);self.a.refresh_from_db()
        self.assertEqual(ability_bonus(computed(self.a),attack,'damage'),2)
        spell=Entry(name='Заклинание',data={'keywords':['Ближний']})
        self.assertEqual(ability_bonus(computed(self.a),spell,'damage'),0)

    def reload_setup(self,action='малым'):
        weapon=Item.objects.create(character=self.a,name='Арбалет',equipped=True,data={'item_type':'weapon','dice':'1к10','keywords':['Дальнобойный 10','Перезарядка '+action],'families':['Арбалеты'],'no_proficiency':True})
        self.a.runtime['weapon_id']=weapon.id;self.a.save()
        attack=Entry.objects.create(kind='ability',name='Выстрел',data={'weapon':True,'damage':True,'formula':'1Ор + Мод','action':'main','circle':0,'keywords':['Дальнобойный 10']})
        self.a.abilities.add(attack)
        scene=self.start()
        p={'op':'ability.use','character':self.a.id,'ability':attack.id,'targets':[],'outcome':'hit','roll_result':'8'}
        reload={'op':'weapon.reload','character':self.a.id,'item':weapon.id}
        return weapon,attack,scene,p,reload

    def test_crossbow_miss_requires_reload_and_undo_restores_both_resources(self):
        from .rules import availability
        weapon,attack,scene,p,reload=self.reload_setup()
        self.post(self.alice,{**p,'outcome':'miss'})
        weapon.refresh_from_db();self.assertTrue(weapon.data['needs_reload'])
        self.a.refresh_from_db();self.a.runtime['actions']['main']=1;self.a.save()
        self.assertEqual(availability(self.a,attack,scene),'Перезарядите оружие')
        self.post(self.alice,p,400)
        self.post(self.alice,reload);weapon.refresh_from_db();self.a.refresh_from_db()
        self.assertFalse(weapon.data['needs_reload']);self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.post(self.alice,{'op':'undo'});weapon.refresh_from_db();self.a.refresh_from_db()
        self.assertTrue(weapon.data['needs_reload']);self.assertEqual(self.a.runtime['actions']['minor'],1)
        self.post(self.alice,{'op':'redo'});weapon.refresh_from_db();self.assertFalse(weapon.data['needs_reload'])
        self.post(self.alice,p);weapon.refresh_from_db();self.assertTrue(weapon.data['needs_reload'])
        self.post(self.alice,{'op':'undo'});weapon.refresh_from_db();self.assertFalse(weapon.data['needs_reload'])

    def test_winch_crossbow_reloads_with_main_action_and_keeps_charge_between_turns(self):
        weapon,attack,scene,p,reload=self.reload_setup('действием')
        self.post(self.alice,p);self.post(self.alice,reload,400)
        self.turn(scene,self.alice);self.post(self.alice,reload,400)
        self.turn(scene,self.bob);self.a.refresh_from_db()
        self.assertTrue(computed(self.a)['needs_reload'])
        self.post(self.alice,reload);self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],0)
        self.assertEqual(self.a.runtime['actions']['minor'],1)
        self.assertFalse(computed(self.a)['needs_reload'])

    def test_reloading_permissions_stun_and_selected_weapon_are_checked(self):
        weapon,attack,scene,p,reload=self.reload_setup()
        self.post(self.alice,reload,400)
        self.post(self.alice,p)
        self.post(self.bob,reload,403)
        self.post(self.alice,{**reload,'item':0},400)
        self.a.refresh_from_db();self.a.runtime['stun_pending']=1;self.a.save()
        self.post(self.alice,reload,400);self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['minor'],1)
        weapon.refresh_from_db();self.assertTrue(weapon.data['needs_reload'])

    def test_switching_weapon_preserves_reload_and_does_not_block_spells(self):
        from .rules import availability
        weapon,attack,scene,p,reload=self.reload_setup();self.post(self.alice,p)
        other=Item.objects.create(character=self.a,name='Второй арбалет',equipped=True,data=weapon.data.copy())
        self.post(self.alice,{'op':'weapon.select','character':self.a.id,'item':other.id})
        self.a.refresh_from_db();self.assertFalse(computed(self.a)['needs_reload'])
        self.post(self.alice,{'op':'weapon.select','character':self.a.id,'item':weapon.id})
        self.a.refresh_from_db();self.assertTrue(computed(self.a)['needs_reload'])
        self.a.runtime['actions']['main']=1;self.a.save()
        spell=Entry(name='Заклинание',data={'formula':'1к6','damage':True})
        self.assertEqual(availability(self.a,spell,scene),'')

    def test_mark_penalty_uses_all_attack_targets(self):
        from .targeting import resolve
        self.a.runtime['effects']=[{'key':'status:Метка','name':'Метка','stat':'status','value':1,'source_id':self.b.id,'duration':'turns','remaining':1}]
        self.a.save()
        attack=Entry(name='Атака',data={'damage':True,'formula':'1к6'})
        calc=computed(self.a)
        self.assertEqual(resolve(self.a,attack,calc,[],{})[0]['mark_penalty'],-3)
        self.assertEqual(resolve(self.a,attack,calc,[self.a],{})[0]['mark_penalty'],-3)
        rows=resolve(self.a,attack,calc,[self.a,self.b],{})
        self.assertEqual([r['mark_penalty'] for r in rows],[0,0])
        self.assertEqual(resolve(self.a,attack,calc,[],{'mark_source_included':True})[0]['mark_penalty'],-3)
        self.assertEqual(calc['hit'],0)

    def test_external_mark_source_is_explicit_and_only_affects_hit(self):
        from .targeting import resolve
        self.a.runtime['effects']=[{'key':'mark','name':'Метка','stat':'status','value':1,'source_id':None}];self.a.save()
        attack=Entry(name='Атака',data={'damage':True,'formula':'2к6'})
        calc=computed(self.a)
        before=resolve(self.a,attack,calc,[],{})[0]
        after=resolve(self.a,attack,calc,[],{'mark_source_included':True})[0]
        self.assertEqual(after['hit']-before['hit'],3)
        self.assertEqual(after['damage'],before['damage'])
        with self.assertRaises(ValueError):resolve(self.a,attack,calc,[],{'mark_source_included':'yes'})

    def test_master_mark_source_and_target_turn_expiry(self):
        scene=self.start()
        self.post(self.gm,{'op':'effect.apply','character':self.a.id,'name':'Метка','value':1,'turns':1,'source_id':self.b.id})
        self.a.refresh_from_db();effect=self.a.runtime['effects'][0]
        self.assertEqual(effect['source_id'],self.b.id);self.assertEqual(effect['source'],self.b.name)
        self.turn(scene,self.alice);self.a.refresh_from_db();self.assertEqual(self.a.runtime['effects'],[])
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['effects'][0]['source_id'],self.b.id)

    def test_mark_import_handles_inflection_without_importing_mark_of_corruption(self):
        from .book_effects import literal_effects
        for word in ['Метка','Метку']:
            effects,target=literal_effects('Цель получает 1к6 урона и '+word+' на 1 ход.')
            self.assertEqual(len(effects),1)
            self.assertEqual((effects[0]['name'],effects[0]['turns']),('Метка',1))
        self.assertEqual(literal_effects('Цель получает эффект Метка Порчи на 3 хода.')[0],[])

    def test_book_sleep_and_fear_have_correct_explicit_and_default_durations(self):
        for name,status,turns in [('Затуманенный разум','Сон',2),('Ужасающий удар','Страх',1)]:
            desc,data,source=self.book_row(name)
            effects=[e for e in data.get('effects',[]) if e.get('name')==status]
            self.assertEqual(len(effects),1,name)
            self.assertEqual(effects[0]['turns'],turns)
        from .book_effects import literal_effects
        self.assertEqual(literal_effects('Цель получает эффект Сон.')[0][0]['turns'],1)
        self.assertEqual(literal_effects('Цель получает эффект Страх на 3 хода.')[0][0]['turns'],3)

    def test_sleep_blocks_actions_and_expires_after_two_target_turns(self):
        from .rules import availability
        scene=self.start();self.a.refresh_from_db()
        self.post(self.gm,{'op':'effect.apply','character':self.a.id,'name':'Сон','value':1,'turns':2})
        self.a.refresh_from_db()
        self.assertIn('пропускает ход',availability(self.a,self.bless,scene))
        for action in ['main','minor','move']:
            self.post(self.alice,{'op':'action.spend','character':self.a.id,'action':action},400)
        self.post(self.alice,{'op':'action.spend','character':self.a.id,'action':'main','exchange':'minor'},400)
        self.turn(scene,self.alice);self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['effects'][0]['remaining'],1)
        self.assertEqual(Event.objects.latest('id').inputs['skipped_conditions'][0]['name'],'Сон')
        self.turn(scene,self.bob);self.turn(scene,self.alice);self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['effects'],[])
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['effects'][0]['remaining'],1)

    def test_damage_to_temporary_hp_wakes_sleep_and_undo_restores_it(self):
        self.start();self.a.refresh_from_db();self.a.runtime['temp']=5;self.a.save()
        self.post(self.gm,{'op':'effect.apply','character':self.a.id,'name':'Сон','value':1,'turns':2})
        self.a.refresh_from_db();hp=self.a.runtime['hp']
        self.post(self.gm,{'op':'hp','character':self.a.id,'mode':'damage','value':0})
        self.a.refresh_from_db();self.assertEqual(len(self.a.runtime['effects']),1)
        self.post(self.gm,{'op':'hp','character':self.a.id,'mode':'damage','value':2})
        self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['effects'],[])
        self.assertEqual((self.a.runtime['hp'],self.a.runtime['temp']),(hp,3))
        self.post(self.gm,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(len(self.a.runtime['effects']),1)
        self.assertEqual(self.a.runtime['temp'],5)

    def test_fear_skip_records_source_and_current_speed_without_moving_hp(self):
        scene=self.start()
        self.post(self.gm,{'op':'effect.apply','character':self.a.id,'name':'Страх','value':1,'turns':1,'source_id':self.b.id})
        self.a.refresh_from_db();hp=self.a.runtime['hp']
        self.turn(scene,self.alice)
        row=Event.objects.latest('id').inputs['skipped_conditions'][0]
        self.assertEqual(row,{'name':'Страх','source':self.b.name,'speed':6})
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],hp)
        self.assertEqual(self.a.runtime['effects'],[])

    def weave_setup(self):
        prepare=Entry.objects.create(kind='ability',name='Мистическое плетение',data={'circle':1,'action':'minor','category':'active'})
        attack=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'damage':True,'formula':'1Ор','action':'main','circle':0})
        spell=Entry.objects.create(kind='ability',name='Световая вспышка',data={'circle':1,'category':'active','action':'main','keywords':['Свет','Дальнобойный 5'],'target':'single','effects':[{'stat':'temp','value':5}]})
        self.a.abilities.add(prepare,spell);self.a.level=8;self.a.save()
        scene=self.start()
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':prepare.id,'targets':[]})
        p={'op':'ability.use','character':self.a.id,'ability':attack.id,'targets':[self.b.id],'roll_result':'15','outcome':'miss',
           'weave':{'ability':spell.id,'targets':[self.b.id],'outcome':'hit'}}
        return scene,prepare,attack,spell,p

    def test_weaving_combines_attack_and_spell_in_one_undoable_event(self):
        scene,prepare,attack,spell,p=self.weave_setup()
        count=Event.objects.count();self.post(self.alice,p)
        self.assertEqual(Event.objects.count(),count+1)
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['main'],0)
        self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.assertEqual(self.a.runtime['used'][str(spell.pk)],1)
        self.assertEqual(self.b.runtime['temp'],5)
        self.assertNotIn('mystic_weaving',self.a.runtime)
        self.assertEqual(Event.objects.latest('id').inputs['weaving']['spell'],spell.name)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertIn('mystic_weaving',self.a.runtime)
        self.assertEqual(self.a.runtime['actions']['main'],1)
        self.assertEqual(self.b.runtime['temp'],0)
        self.assertNotIn(str(spell.pk),self.a.runtime['used'])
        self.post(self.alice,{'op':'redo'});self.b.refresh_from_db();self.assertEqual(self.b.runtime['temp'],5)

    def test_invalid_woven_spell_rolls_back_attack_and_all_resources(self):
        scene,prepare,attack,spell,p=self.weave_setup()
        self.a.refresh_from_db();before=json.loads(json.dumps(self.a.runtime));count=Event.objects.count()
        for child in [{**p['weave'],'targets':[self.a.id]}, {**p['weave'],'ability':attack.pk}, {**p['weave'],'as_reaction':True}]:
            self.post(self.alice,{**p,'weave':child},400)
            self.a.refresh_from_db();self.assertEqual(self.a.runtime,before)
            self.assertEqual(Event.objects.count(),count)
        spell.data['rolls']=True;spell.save()
        self.post(self.alice,p,400);self.a.refresh_from_db();self.assertEqual(self.a.runtime,before)

    def test_weaving_area_requires_center_and_uses_selected_recipients(self):
        scene,prepare,attack,spell,p=self.weave_setup()
        spell.data.update(keywords=['Свет','Сфера 2 в 5'],target='multiple');spell.save()
        child={**p['weave'],'targets':[self.a.pk,self.b.pk]}
        self.post(self.alice,{**p,'weave':child},400)
        self.post(self.alice,{**p,'weave':{**child,'area_center_confirmed':True}})
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual((self.a.runtime['temp'],self.b.runtime['temp']),(5,5))
        self.assertEqual(Event.objects.latest('id').inputs['weaving']['center'],[self.b.pk])

    def test_weaving_optional_spell_is_consumed_only_by_next_standard_attack(self):
        scene,prepare,attack,spell,p=self.weave_setup()
        self.post(self.alice,{k:v for k,v in p.items() if k!='weave'})
        self.a.refresh_from_db();self.assertNotIn('mystic_weaving',self.a.runtime)
        self.assertNotIn(str(spell.pk),self.a.runtime['used'])
        self.a.runtime['actions']['main']=1;self.a.save()
        self.post(self.alice,p,400)

    def test_weaving_cannot_use_exhausted_spell_or_skip_its_physical_dice(self):
        scene,prepare,attack,spell,p=self.weave_setup()
        from .rules import limit
        self.a.refresh_from_db();self.a.runtime['used'][str(spell.id)]=limit(self.a.level,1);self.a.save()
        before=json.loads(json.dumps(self.a.runtime))
        self.post(self.alice,p,400);self.a.refresh_from_db();self.assertEqual(self.a.runtime,before)

    def test_woven_pool_preserves_dice_allocations_and_manual_healing(self):
        scene,prepare,attack,spell,p=self.weave_setup()
        spell.name='Исход небес';spell.data.update(keywords=['Свет','Вокруг 3'],effects=[],target='multiple');spell.save()
        child={'ability':spell.pk,'area_center_confirmed':True,'dice':[1,2,3,4,5,6],
               'dice_targets':[self.a.pk,None,self.b.pk,None,self.b.pk,None]}
        self.post(self.alice,{**p,'weave':child});self.a.refresh_from_db();self.b.refresh_from_db()
        pending=next(iter(self.a.runtime['pending_heals'].values()))
        self.assertEqual(pending['allocations'],[{'character':self.a.pk,'hp':1},{'character':self.b.pk,'hp':8}])
        self.assertEqual((self.a.runtime['hp'],self.b.runtime['hp']),(10,10))
        event=Event.objects.latest('id');self.assertEqual(event.inputs['weaving']['inputs']['roll_pool']['damage_pool'],12)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertFalse(self.a.runtime.get('pending_heals'))

    def support_setup(self,mode='Земля',mastery=False):
        support=Entry.objects.create(kind='ability',name='Стихийная поддержка',data={'circle':1,'category':'active','action':'main','formula':'Мод','damage':True,'rolls':True})
        self.a.abilities.add(support)
        if mastery:self.a.abilities.add(Entry.objects.create(kind='ability',name='Стихийное превосходство',data={'category':'passive'}))
        self.a.level=8;self.a.save();scene=self.start()
        self.post(self.alice,{'op':'ability.use','character':self.a.id,'ability':support.pk,'stance_mode':mode,'targets':[]})
        self.a.refresh_from_db()
        return support,scene

    def test_support_switch_changes_ac_step_and_undo_without_spending_another_use(self):
        support,scene=self.support_setup()
        self.assertEqual(computed(self.a)['ac'],7)
        self.assertEqual(self.a.runtime['actions']['main'],0)
        self.post(self.alice,{'op':'stance.switch','character':self.a.id,'stance_mode':'Воздух'})
        self.a.refresh_from_db();calc=computed(self.a)
        self.assertEqual((calc['ac'],calc['step']),(5,3))
        self.assertEqual(self.a.runtime['actions']['minor'],0)
        self.assertEqual(self.a.runtime['used'][str(support.pk)],1)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(computed(self.a)['ac'],7)
        self.assertEqual(self.a.runtime['actions']['minor'],1)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db();self.assertEqual(computed(self.a)['step'],3)

    def test_support_fire_applies_only_to_unlimited_damage_without_multiplying_on_crit(self):
        support,scene=self.support_setup('Огонь')
        ability=Entry(name='Огонь',data={'damage':True,'formula':'1к6','circle':0})
        self.assertEqual(formula(self.a,ability),'1к6 +3')
        self.assertEqual(formula(self.a,ability,True),'2к6 +3')
        ability.data['circle']=1;self.assertEqual(formula(self.a,ability),'1к6')
        support.archived=True;support.save();ability.data['circle']=0
        self.assertEqual(formula(self.a,ability),'1к6')

    def test_support_water_uses_mod_manual_healing_once_per_global_turn(self):
        support,scene=self.support_setup('Вода')
        p={'op':'stance.water','character':self.a.pk,'target':self.b.pk,'in_range':True}
        self.post(self.alice,{**p,'in_range':False},400)
        self.post(self.alice,p);self.a.refresh_from_db();self.b.refresh_from_db()
        pending=next(iter(self.a.runtime['pending_heals'].values()))
        self.assertEqual(pending['allocations'],[{'character':self.b.pk,'hp':3}])
        self.assertEqual(self.b.runtime['hp'],10)
        self.post(self.alice,p,400)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertFalse(self.a.runtime.get('pending_heals'))
        self.post(self.alice,p)
        self.turn(scene,self.alice);self.post(self.alice,p)

    def test_support_mastery_changes_activation_cost_resistance_and_water_cleanse(self):
        support,scene=self.support_setup('Земля',mastery=True)
        self.assertEqual((self.a.runtime['actions']['main'],self.a.runtime['actions']['minor']),(1,0))
        self.assertEqual(computed(self.a)['resistance'],3)
        self.turn(scene,self.alice);self.turn(scene,self.bob)
        self.post(self.alice,{'op':'stance.switch','character':self.a.id,'stance_mode':'Вода'})
        self.b.refresh_from_db();self.b.runtime['effects']=[{'key':'slow','name':'Замедление','stat':'speed','value':-2,'duration':'turns','remaining':3}];self.b.save()
        self.post(self.alice,{'op':'stance.water','character':self.a.pk,'target':self.b.pk,'in_range':True,'remove':'slow'})
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db();self.assertEqual(len(self.b.runtime['effects']),1)

    def test_support_switch_permissions_and_turn_are_enforced(self):
        support,scene=self.support_setup()
        p={'op':'stance.switch','character':self.a.id,'stance_mode':'Вода'}
        self.post(self.bob,p,403)
        self.post(self.alice,{**p,'stance_mode':'Тьма'},400)
        self.turn(scene,self.alice);self.post(self.alice,p,400)

    def fire_minor_setup(self):
        support,scene=self.support_setup('Огонь',mastery=True)
        self.a.refresh_from_db();self.a.runtime['actions'].update(main=0,minor=1);self.a.save()
        attack=Entry.objects.create(kind='ability',name='Искра',data={'category':'active','action':'main','circle':0,'damage':True,'formula':'1к6','keywords':['Огонь']})
        self.a.abilities.add(attack)
        return scene,attack,{'op':'ability.use','character':self.a.id,'ability':attack.id,'targets':[],
                            'support_minor':True,'outcome':'hit','roll_result':'Попадание 15, урон 6'}

    def test_fire_mastery_attack_uses_minor_when_main_is_exhausted_and_undo_restores_it(self):
        from .views import serialize_char
        scene,attack,p=self.fire_minor_setup()
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==attack.pk)
        self.assertEqual(row['reason'],'Нет нужного действия')
        self.assertEqual(row['support_minor_reason'],'')
        self.assertEqual(row['formula'],'1к6 +3')
        self.post(self.alice,p);self.a.refresh_from_db()
        self.assertEqual((self.a.runtime['actions']['main'],self.a.runtime['actions']['minor']),(0,0))
        self.assertTrue(Event.objects.latest('id').inputs['support_minor'])
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual((self.a.runtime['actions']['main'],self.a.runtime['actions']['minor']),(0,1))
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['actions']['minor'],0)

    def test_fire_minor_cannot_bypass_stance_mastery_circle_or_reaction(self):
        scene,attack,p=self.fire_minor_setup()
        self.post(self.alice,{**p,'as_reaction':True},400)
        attack.data['circle']=1;attack.save();self.post(self.alice,p,400)
        attack.data.update(circle=0,action='reaction');attack.save();self.post(self.alice,p,400)
        attack.data['action']='main';attack.save()
        self.a.runtime['elemental_support']['mode']='Земля';self.a.save();self.post(self.alice,p,400)
        self.a.runtime['elemental_support']['mode']='Огонь';self.a.save()
        self.a.abilities.remove(Entry.objects.get(name='Стихийное превосходство'));self.post(self.alice,p,400)
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['minor'],1)

    def test_fire_minor_requires_own_turn_and_a_minor_resource(self):
        scene,attack,p=self.fire_minor_setup()
        self.post(self.alice,p)
        self.post(self.alice,p,400)
        self.turn(scene,self.alice);self.post(self.alice,p,400)

    def test_fire_minor_does_not_mutate_catalogue_action_or_allow_non_attacks(self):
        scene,attack,p=self.fire_minor_setup()
        self.post(self.alice,p);attack.refresh_from_db()
        self.assertEqual(attack.data['action'],'main')
        self.post(self.alice,{'op':'undo'})
        attack.data['damage']=False;attack.save();self.post(self.alice,p,400)

    def fire_water_setup(self):
        passive=Entry.objects.create(kind='ability',name='Огонь и Вода',data={'category':'passive'})
        ability=Entry.objects.create(kind='ability',name='Влажный удар',data={'action':'main','category':'active','circle':0,'damage':True,'formula':'1к6','target':'single','effects':[{'name':'Влага','stat':'status','value':2,'turns':3}]})
        self.a.abilities.add(passive,ability);scene=self.start()
        p={'op':'ability.use','character':self.a.id,'ability':ability.id,'targets':[self.b.id],'roll_result':'13','outcome':'hit'}
        return passive,ability,scene,p

    def test_fire_water_bonus_is_visible_and_applied_once_without_changing_catalogue(self):
        from .views import serialize_char
        passive,ability,scene,p=self.fire_water_setup()
        self.a.refresh_from_db()
        for _ in range(2):
            row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==ability.id)
            self.assertEqual(row['data']['effects'][0]['value'],3)
            self.assertEqual(row['data']['effects'][0]['base_value'],2)
        self.post(self.alice,p);self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['effects'][0]['value'],3)
        ability.refresh_from_db();self.assertEqual(ability.data['effects'][0]['value'],2)
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])

    def test_fire_water_bonus_enters_reaction_strength_before_combination(self):
        passive,ability,scene,p=self.fire_water_setup()
        self.b.refresh_from_db();self.b.runtime['effects']=[{'key':'shock','name':'Шок','status':'Шок','stat':'status','value':2,'duration':'turns','remaining':2}];self.b.save()
        self.post(self.alice,{**p,'reactions':{f'{self.b.pk}:0':'shock'}})
        self.b.refresh_from_db();effect=self.b.runtime['effects'][0]
        self.assertEqual((effect['name'],effect['value'],effect['duration']),('Оцепенение',5,'actions'))

    def test_fire_water_miss_external_target_and_archived_passive(self):
        from .stances import effective
        passive,ability,scene,p=self.fire_water_setup()
        self.post(self.alice,{**p,'outcome':'miss'});self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])
        self.post(self.alice,{'op':'undo'})
        self.post(self.alice,{**p,'targets':[]})
        self.assertEqual(Event.objects.latest('id').inputs['external_effects'][0]['value'],3)
        self.post(self.alice,{'op':'undo'})
        passive.archived=True;passive.save()
        self.post(self.alice,p);self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['value'],2)

    def test_fire_water_only_strengthens_its_two_statuses(self):
        from .stances import effective
        passive,ability,scene,p=self.fire_water_setup()
        ability.data['effects']=[{'name':name,'stat':'status','value':2} for name in ['Поджог','Влага','Шок','Сон']]
        ability.data['effects'].append({'name':'Поджог','stat':'status','value':2,'manual':True})
        transformed=effective(self.a,ability)
        self.assertEqual([e['value'] for e in transformed.data['effects']],[3,3,2,2,2])
        self.assertEqual([e['value'] for e in effective(self.a,transformed).data['effects']],[3,3,2,2,2])

    def test_necroflame_records_double_strength_as_start_turn_damage(self):
        from .statuses import apply_status
        from .periodic import damage_events
        self.b.runtime['effects']=[{'key':'curse','name':'Проклятье','stat':'hit','value':-2,'duration':'turns','remaining':3}]
        apply_status(self.b,{'name':'Поджог','stat':'status','value':3,'duration':'turns','remaining':3},'curse')
        effect=self.b.runtime['effects'][0]
        self.assertEqual((effect['name'],effect['value']),('Некропламя',5))
        self.assertIn('10 продолжительного урона',effect['note'])
        self.assertEqual(damage_events(self.b,'start')[0]['damage'],10)
        self.assertEqual(damage_events(self.b,'end'),[])

    def test_periodic_end_tick_occurs_before_expiry_and_next_start_is_logged(self):
        scene=self.start();self.a.refresh_from_db();self.b.refresh_from_db()
        self.a.runtime['effects']=[{'key':'poison','name':'Яд','stat':'status','value':2,'duration':'turns','remaining':1}]
        self.b.runtime['effects']=[{'key':'burn','name':'Поджог','stat':'status','value':3,'duration':'turns','remaining':1}]
        self.a.save();self.b.save()
        hp=(self.a.runtime['hp'],self.b.runtime['hp'])
        self.turn(scene,self.alice)
        rows=Event.objects.latest('id').inputs['periodic_damage']
        self.assertEqual([(r['effect'],r['phase'],r['damage'],r['character']) for r in rows],[('Яд','end',2,self.a.pk),('Поджог','start',3,self.b.pk)])
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.a.runtime['effects'],[])
        self.assertEqual((self.a.runtime['hp'],self.b.runtime['hp']),hp)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db()
        self.assertEqual(self.a.runtime['effects'][0]['remaining'],1)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['effects'],[])

    def test_periodic_area_reactions_show_scope_and_do_not_confuse_ability_names(self):
        from .periodic import damage_events
        self.a.runtime['effects']=[{'name':'Священное пламя','status':'Священное пламя','stat':'status','value':4},
                                   {'name':'Вирус','status':'Вирус','stat':'status','value':2},
                                   {'name':'Священное пламя','stat':'target_hit','value':1}]
        rows=damage_events(self.a)
        self.assertEqual([(r['effect'],r['area'],r['damage']) for r in rows],[('Священное пламя',1,4),('Вирус',1,2)])

    def test_periodic_damage_preview_lists_phases_and_zero_damage_is_omitted(self):
        from .views import serialize_char
        self.a.runtime['effects']=[{'key':'blood','name':'Кровотечение','stat':'status','value':3},
                                   {'key':'dot','name':'Продолжительный урон','stat':'status','value':4},
                                   {'key':'burn','name':'Поджог','stat':'status','value':0}]
        rows=serialize_char(self.a,self.alice)['periodic_damage']
        self.assertEqual([(r['phase'],r['damage'],r['damage_type']) for r in rows],[('end',3,'Физический'),('start',4,'')])

    def hyperthermia_setup(self):
        scene=self.start();self.a.refresh_from_db()
        self.a.runtime['effects']=[{'key':'heat','name':'Гипертермия','status':'Гипертермия','stat':'status','value':5,'duration':'turns','remaining':3}]
        self.a.save()
        return scene

    def test_hyperthermia_actions_misses_free_reactions_and_undo(self):
        scene=self.hyperthermia_setup()
        for action in ['main','minor','move','reaction','free']:
            with self.subTest(action=action):
                scene.state['turn']=scene.state['order'].index(self.b.pk if action=='reaction' else self.a.pk);scene.save()
                ability=Entry.objects.create(kind='ability',name='Проверка '+action,data={'category':'active','action':action,'circle':0,'damage':True,'formula':'1к4','rolls':True})
                self.a.abilities.add(ability)
                self.post(self.alice,{'op':'ability.use','character':self.a.pk,'ability':ability.pk,'targets':[],'outcome':'miss','roll_result':'2'})
                event=Event.objects.latest('id');rows=event.inputs['periodic_damage']
                self.assertEqual([(r['damage'],r['action']) for r in rows],[(5,action)])
                self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],10)
                self.post(self.alice,{'op':'undo'});event.refresh_from_db();self.assertTrue(event.undone)
                self.post(self.alice,{'op':'redo'});event.refresh_from_db();self.assertFalse(event.undone)
                self.assertEqual(event.inputs['periodic_damage'],rows)
                self.post(self.alice,{'op':'undo'})

    def test_hyperthermia_only_performed_actions_not_exchange_skip_or_turn(self):
        scene=self.hyperthermia_setup()
        self.post(self.alice,{'op':'action.spend','character':self.a.pk,'action':'move'})
        self.assertEqual(Event.objects.latest('id').inputs['periodic_damage'][0]['damage'],5)
        self.post(self.alice,{'op':'undo'})
        self.post(self.alice,{'op':'action.spend','character':self.a.pk,'action':'main','exchange':'minor'})
        self.assertNotIn('periodic_damage',Event.objects.latest('id').inputs)
        self.post(self.alice,{'op':'undo'})
        self.a.refresh_from_db();self.a.runtime['effects'].append({'key':'stun','status':'Оглушение','name':'Оглушение','value':1,'duration':'actions'})
        self.a.runtime['stun_pending']=1;self.a.save()
        self.post(self.alice,{'op':'action.spend','character':self.a.pk,'action':'main'})
        self.assertNotIn('periodic_damage',Event.objects.latest('id').inputs)
        self.turn(scene,self.alice)
        self.assertFalse(any(r['effect']=='Гипертермия' for r in Event.objects.latest('id').inputs['periodic_damage']))

    def test_hyperthermia_readied_action_counts_reserving_and_performing_separately(self):
        self.hyperthermia_setup()
        self.post(self.alice,{'op':'action.ready','character':self.a.pk,'action':'main','condition':'Враг подошёл'})
        self.assertEqual([r['action'] for r in Event.objects.latest('id').inputs['periodic_damage']],['minor'])
        self.a.refresh_from_db();key=self.a.runtime['readied']['key']
        self.post(self.alice,{'op':'action.perform_ready','character':self.a.pk,'ready_id':key,'triggered':True,'dex_roll':15})
        self.assertEqual([r['action'] for r in Event.objects.latest('id').inputs['periodic_damage']],['main'])

    def test_hyperthermia_reaction_strength_preview_and_new_effect_does_not_tick_retroactively(self):
        from .statuses import apply_status
        from .views import serialize_char
        scene=self.start();self.a.refresh_from_db()
        self.a.runtime['effects']=[{'key':'fire','name':'Поджог','stat':'status','value':2,'duration':'turns','remaining':3}];self.a.save()
        ability=Entry.objects.create(kind='ability',name='Яд на себя',data={'category':'active','action':'minor','circle':0,'rolls':False,'effects':[{'name':'Яд','stat':'status','value':3,'duration':'turns','turns':3}]})
        self.a.abilities.add(ability)
        self.post(self.alice,{'op':'ability.use','character':self.a.pk,'ability':ability.pk,'targets':[self.a.pk],'reactions':{f'{self.a.pk}:0':'fire'}})
        self.assertNotIn('periodic_damage',Event.objects.latest('id').inputs)
        self.a.refresh_from_db();rows=serialize_char(self.a,self.alice)['periodic_damage']
        self.assertEqual([(r['effect'],r['phase'],r['damage']) for r in rows],[('Гипертермия','action',5)])
        self.post(self.alice,{'op':'action.spend','character':self.a.pk,'action':'main'})
        self.assertEqual(Event.objects.latest('id').inputs['periodic_damage'][0]['damage'],5)

    def test_hyperthermia_reload_counts_an_action(self):
        weapon,attack,scene,p,reload=self.reload_setup()
        self.a.refresh_from_db();self.a.runtime['effects']=[{'key':'heat','status':'Гипертермия','value':4}];self.a.save()
        self.post(self.alice,p)
        self.assertEqual(len(Event.objects.latest('id').inputs['periodic_damage']),1)
        self.post(self.alice,reload)
        self.assertEqual([(r['damage'],r['action']) for r in Event.objects.latest('id').inputs['periodic_damage']],[(4,'minor')])
        self.post(self.alice,{'op':'undo'});weapon.refresh_from_db();self.assertTrue(weapon.data['needs_reload'])

    def test_hyperthermia_woven_attack_counts_one_action(self):
        scene,prepare,attack,spell,p=self.weave_setup()
        self.a.refresh_from_db();self.a.runtime['effects']=[{'key':'heat','status':'Гипертермия','value':4}];self.a.save()
        self.post(self.alice,p)
        self.assertEqual([(r['damage'],r['action']) for r in Event.objects.latest('id').inputs['periodic_damage']],[(4,'main')])
        self.assertNotIn('periodic_damage',Event.objects.latest('id').inputs['weaving'])

    def test_saturation_instant_strengthens_selected_element_and_refreshes_duration(self):
        from .statuses import apply_status, reaction_options
        self.a.runtime['effects']=[{'key':'curse','name':'Проклятье','stat':'hit','value':-2,'duration':'turns','remaining':1,'max_turns':5}, {'key':'wet','name':'Влага','stat':'status','value':1,'duration':'turns','remaining':2}]
        incoming={'name':'Насыщение','stat':'status','value':3}
        self.assertEqual([r['key'] for r in reaction_options(self.a,incoming)],['curse','wet'])
        apply_status(self.a,incoming,'curse')
        curse=next(e for e in self.a.runtime['effects'] if e['key']=='curse')
        self.assertEqual((curse['value'],curse['remaining']),(-5,5))
        self.assertEqual(len(self.a.runtime['effects']),2)
        self.a.runtime['effects']=[];apply_status(self.a,incoming)
        self.assertEqual(self.a.runtime['effects'],[])

    def test_saturation_supports_constructive_effects_without_changing_duration_kind(self):
        from .statuses import apply_status
        for name,duration in [('Некропламя','battle'),('Заморозка','actions')]:
            self.a.runtime['effects']=[{'key':'e','status':name,'value':2,'duration':duration}]
            apply_status(self.a,{'name':'Насыщение','stat':'status','value':1},'e')
            self.assertEqual(self.a.runtime['effects'][0]['value'],3)
            self.assertEqual(self.a.runtime['effects'][0]['duration'],duration)
            self.assertNotIn('remaining',self.a.runtime['effects'][0])

    def test_saturation_ability_requires_choice_and_supports_undo(self):
        from .book_effects import literal_effects
        scene=self.start();self.b.refresh_from_db()
        self.b.runtime['effects']=[{'key':'wet','name':'Влага','stat':'status','value':2,'duration':'turns','remaining':1}];self.b.save()
        effects,target=literal_effects('Цель получает Насыщение 3.')
        ability=Entry.objects.create(kind='ability',name='Усиление',data={'category':'active','action':'main','circle':0,'effects':effects,'target':target,'rolls':False})
        self.a.abilities.add(ability)
        p={'op':'ability.use','character':self.a.pk,'ability':ability.pk,'targets':[self.b.pk]}
        self.post(self.alice,p,400)
        self.post(self.alice,{**p,'reactions':{f'{self.b.pk}:0':'wet'}})
        self.b.refresh_from_db();self.assertEqual((self.b.runtime['effects'][0]['value'],self.b.runtime['effects'][0]['remaining']),(5,3))
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db()
        self.assertEqual((self.b.runtime['effects'][0]['value'],self.b.runtime['effects'][0]['remaining']),(2,1))

    def test_superconductor_target_formula_uses_physical_weapon_units_and_not_critical_dice(self):
        from .targeting import resolve
        ability=Entry.objects.create(kind='ability',name='Удар',description='Цель получает 2Ор+Мод Физического урона.',data={'weapon':True,'damage':True,'formula':'2Ор+Мод'})
        Item.objects.create(character=self.a,name='Клинок',equipped=True,data={'item_type':'weapon','dice':'2к4','no_proficiency':True})
        self.b.runtime['effects']=[{'key':'conductor','status':'Сверхпроводник','value':3,'duration':'turns','remaining':3}]
        for outcome in ['hit','critical']:
            row=resolve(self.a,ability,computed(self.a),[self.b],{'outcome':outcome})[0]
            self.assertEqual(row['conductor_damage'],3)
            self.assertIn('+3 [Сверхпроводник]',row['damage'])
        ability.data['damage_type']='Огонь'
        self.assertEqual(resolve(self.a,ability,computed(self.a),[self.b],{})[0]['conductor_damage'],0)
        ability.data['damage_type']='Физический';ability.data['formula']='1Ор'
        self.assertEqual(resolve(self.a,ability,computed(self.a),[self.b],{})[0]['conductor_damage'],1.5)

    def test_superconductor_external_target_validation_and_unarmed_exclusion(self):
        from .targeting import resolve, physical_weapon_units
        from .views import serialize_char
        ability=Entry.objects.create(kind='ability',name='Стандартная атака',data={'system':True,'weapon':True,'damage':True,'formula':'1Ор+Мод'})
        self.assertEqual(physical_weapon_units(ability,computed(self.a)),0)
        Item.objects.create(character=self.a,name='Клинок',equipped=True,data={'item_type':'weapon','dice':'1к6','no_proficiency':True})
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==ability.pk)
        self.assertEqual(row['physical_weapon_units'],1)
        self.assertEqual(resolve(self.a,ability,computed(self.a),[],{'external_conductor':4})[0]['conductor_damage'],2)
        for payload,targets in [({'external_conductor':-1},[]),({'external_conductor':True},[]),({'external_conductor':4},[self.b])]:
            with self.assertRaises(ValueError):resolve(self.a,ability,computed(self.a),targets,payload)

    def test_superconductor_attack_captures_preexisting_effect_and_undo(self):
        scene=self.start();self.b.refresh_from_db()
        self.b.runtime['effects']=[{'key':'conductor','status':'Сверхпроводник','value':4,'duration':'turns','remaining':3}];self.b.save()
        Item.objects.create(character=self.a,name='Клинок',equipped=True,data={'item_type':'weapon','dice':'1к6','no_proficiency':True})
        ability=Entry.objects.create(kind='ability',name='Удар',description='Цель получает 2Ор Физического урона.',data={'weapon':True,'damage':True,'formula':'2Ор','action':'main','circle':0})
        self.a.abilities.add(ability)
        self.post(self.alice,{'op':'ability.use','character':self.a.pk,'ability':ability.pk,'targets':[self.b.pk],'outcome':'hit','roll_result':'14'})
        row=Event.objects.latest('id').inputs['attack_targets'][0]
        self.assertEqual(row['conductor_damage'],4)
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['hp'],10)
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['main'],1)

    def instant_reaction_setup(self,old_name,new_name):
        scene=self.start();self.b.refresh_from_db()
        from .statuses import STATUS
        stat,sign=STATUS[old_name]
        self.b.runtime['effects']=[{'key':'old','name':old_name,'stat':stat,'value':sign*2,'duration':'turns','remaining':2}];self.b.save()
        stat,sign=STATUS[new_name]
        ability=Entry.objects.create(kind='ability',name='Реакция',data={'category':'active','action':'main','circle':0,'rolls':False,'effects':[{'name':new_name,'stat':stat,'value':sign*3}]})
        self.a.abilities.add(ability)
        return {'op':'ability.use','character':self.a.pk,'ability':ability.pk,'targets':[self.b.pk],'reactions':{f'{self.b.pk}:0':'old'}}

    def test_cursed_discharge_waits_for_roll_and_resolves_once_with_undo(self):
        p=self.instant_reaction_setup('Проклятье','Шок')
        count=Event.objects.count()
        for value in [None,'',4,31,True,'3.5']:
            self.post(self.alice,{**p,'reaction_rolls':{f'{self.b.pk}:0':value}},400)
            self.assertEqual(Event.objects.count(),count)
            self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['key'],'old')
        self.post(self.alice,{**p,'reaction_rolls':{f'{self.b.pk}:0':'18'}})
        row=Event.objects.latest('id').inputs['instant_reactions'][0]
        self.assertEqual((row['name'],row['strength'],row['damage'],row['ignore_resistance']),('Проклятый разряд',5,18,True))
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[]);self.assertEqual(self.b.runtime['hp'],10)
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'][0]['key'],'old')
        self.post(self.alice,{'op':'redo'});self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])

    def test_explosion_is_instant_and_records_physical_area_damage(self):
        p=self.instant_reaction_setup('Влага','Кислота');self.post(self.alice,p)
        row=Event.objects.latest('id').inputs['instant_reactions'][0]
        self.assertEqual((row['name'],row['damage'],row['area']),('Взрыв',5,2))
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[]);self.assertEqual(self.b.runtime['hp'],10)

    def test_icy_darkness_records_source_temp_hp_without_automatic_hp_changes(self):
        p=self.instant_reaction_setup('Проклятье','Мороз');self.post(self.alice,p)
        row=Event.objects.latest('id').inputs['instant_reactions'][0]
        self.assertEqual((row['name'],row['damage'],row['temp_hp'],row['source_id']),('Ледяная тьма',5,10,self.a.pk))
        self.a.refresh_from_db();self.b.refresh_from_db()
        self.assertEqual(self.b.runtime['effects'],[]);self.assertEqual(self.a.runtime['temp'],0)

    def test_manual_cursed_discharge_uses_the_same_roll_validation(self):
        self.instant_reaction_setup('Проклятье','Шок')
        p={'op':'effect.apply','character':self.b.pk,'name':'Шок','value':3,'reaction':'old','source_id':self.a.pk}
        self.post(self.gm,p,400)
        self.post(self.gm,{**p,'reaction_roll':'21'})
        self.assertEqual(Event.objects.latest('id').inputs['instant_reactions'][0]['damage'],21)

    def test_multiple_effects_react_in_order_and_capture_combined_strength(self):
        scene=self.start()
        ability=Entry.objects.create(kind='ability',name='Два эффекта',data={'category':'active','action':'main','circle':0,'rolls':False,'effects':[{'name':'Влага','stat':'status','value':2},{'name':'Шок','stat':'status','value':3}]})
        self.a.abilities.add(ability)
        p={'op':'ability.use','character':self.a.pk,'ability':ability.pk,'targets':[self.b.pk]}
        self.post(self.alice,p,400)
        self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])
        self.post(self.alice,{**p,'reactions':{f'{self.b.pk}:1':'status:Влага'}})
        self.b.refresh_from_db();self.assertEqual([(e['status'],e['value']) for e in self.b.runtime['effects']],[('Оцепенение',5)])
        self.post(self.alice,{'op':'undo'});self.b.refresh_from_db();self.assertEqual(self.b.runtime['effects'],[])

    def test_light_and_reserve_weapons_draw_with_minor_action_and_undo(self):
        self.start()
        for keyword in ['Лёгкое','Легкое','Резервное']:
            item=Item.objects.create(character=self.a,name='Оружие',data={'item_type':'weapon','dice':'1к4','keywords':[keyword]})
            self.post(self.alice,{'op':'item.equip','id':item.pk})
            self.a.refresh_from_db();item.refresh_from_db()
            self.assertEqual((self.a.runtime['actions']['main'],self.a.runtime['actions']['minor']),(1,0))
            self.assertTrue(item.equipped)
            self.assertEqual(Event.objects.latest('id').inputs['equipment_action'],'minor')
            self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();item.refresh_from_db()
            self.assertFalse(item.equipped);self.assertEqual(self.a.runtime['actions']['minor'],1)

    def test_drawing_weapon_obeys_conditions_turn_and_resources(self):
        scene=self.start()
        item=Item.objects.create(character=self.a,name='Кинжал',data={'item_type':'weapon','dice':'1к4','keywords':['Лёгкое']})
        for status in ['Сон','Страх','Оглушение']:
            self.a.refresh_from_db();self.a.runtime['effects']=[{'key':'block','name':status,'status':status,'value':1}]
            self.a.runtime['stun_pending']=int(status=='Оглушение');self.a.save()
            self.post(self.alice,{'op':'item.equip','id':item.pk},400)
            item.refresh_from_db();self.assertFalse(item.equipped)
        self.a.runtime['effects']=[];self.a.runtime['stun_pending']=0;self.a.runtime['actions']['minor']=0;self.a.save()
        self.post(self.alice,{'op':'item.equip','id':item.pk},400)
        self.a.runtime['actions']['minor']=1;self.a.save();self.turn(scene,self.alice)
        self.post(self.alice,{'op':'item.equip','id':item.pk},400)

    def test_quick_draw_property_does_not_make_removing_or_nonweapon_equipment_minor(self):
        from .weaponry import equip_action
        item=Item.objects.create(character=self.a,name='Кинжал',equipped=True,data={'item_type':'weapon','dice':'1к4','keywords':['Лёгкое']})
        self.assertEqual(equip_action(item),'main')
        item.equipped=False;item.data['item_type']='shield'
        self.assertEqual(equip_action(item),'main')
        item.data={'item_type':'weapon','dice':'1к8','keywords':['Метательное 5']}
        self.assertEqual(equip_action(item),'main')

    def test_massive_strikes_turns_melee_into_line_with_weapon_reach(self):
        from .weaponry import effective,keywords
        passive=Entry.objects.create(kind='ability',name='Массивные удары',data={'category':'passive'})
        weapon=Item.objects.create(character=self.a,name='Пика',equipped=True,data={'item_type':'weapon','dice':'1к10','keywords':['Двуручное','Досягаемость 1']})
        ability=Entry.objects.create(kind='ability',name='Удар',data={'weapon':True,'keywords':['Ближний'],'target':'single','formula':'1Ор','damage':True})
        self.assertIn('Ближний 2',keywords(ability,computed(self.a)))
        self.a.abilities.add(passive)
        transformed=effective(self.a,ability)
        self.assertEqual(transformed.data['range'],'Линия 2');self.assertEqual(transformed.data['target'],'multiple')
        self.assertEqual(ability.data['target'],'single')
        passive.archived=True;passive.save();self.assertEqual(effective(self.a,ability).data['target'],'single')

    def test_massive_strikes_accepts_multiple_targets_and_keeps_ranged_spells_single(self):
        from .views import serialize_char
        passive=Entry.objects.create(kind='ability',name='Массивные удары',data={'category':'passive'})
        ability=Entry.objects.create(kind='ability',name='Ближняя магия',data={'category':'active','action':'main','circle':0,'keywords':['Ближний'],'target':'single','effects':[{'name':'Влага','stat':'status','value':2}],'rolls':False})
        self.a.abilities.add(passive,ability);self.start()
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==ability.pk)
        self.assertEqual((row['data']['range'],row['data']['target']),('Линия 1','multiple'))
        self.post(self.alice,{'op':'ability.use','character':self.a.pk,'ability':ability.pk,'targets':[self.a.pk,self.b.pk]})
        self.a.refresh_from_db();self.b.refresh_from_db();self.assertEqual(self.a.runtime['effects'][0]['value'],2);self.assertEqual(self.b.runtime['effects'][0]['value'],2)
        self.post(self.alice,{'op':'undo'})
        ability.data['keywords']=['Дальнобойный 5'];ability.save()
        row=next(a for a in serialize_char(self.a,self.alice)['abilities'] if a['id']==ability.pk)
        self.assertEqual(row['data']['target'],'single')

    def test_throwing_weapon_keeps_throwing_keyword_and_does_not_become_line(self):
        from .weaponry import effective,keywords
        passive=Entry.objects.create(kind='ability',name='Массивные удары',data={'category':'passive'})
        self.a.abilities.add(passive)
        Item.objects.create(character=self.a,name='Кинжал',equipped=True,data={'dice':'1к4','item_type':'weapon','keywords':['Метательное 5']})
        self.a.runtime['attack_mode']='ranged'
        a=Entry(name='Стандартная атака',data={'weapon':True,'system':True,'keywords':['Ближний'],'target':'single'})
        result=effective(self.a,a)
        self.assertEqual(result.data['target'],'single')
        self.assertEqual(keywords(result,computed(self.a)),['Дальнобойный 5','Метательное'])

    def disarm_setup(self):
        Item.objects.create(character=self.a,name='Цепь',equipped=True,data={'item_type':'weapon','dice':'1к4','keywords':['Захват','Досягаемость 1']})
        held=Item.objects.create(character=self.b,name='Меч',equipped=True,data={'item_type':'weapon','dice':'1к8'})
        self.start()
        return held,{'op':'weapon.disarm','character':self.a.pk,'target':self.b.pk,'item':held.pk,'in_range':True,'outcome':'hit','roll_result':'16'}

    def test_disarm_drops_selected_item_and_undo_restores_weapon(self):
        held,p=self.disarm_setup();self.post(self.alice,p)
        held.refresh_from_db();self.b.refresh_from_db();self.a.refresh_from_db()
        self.assertFalse(held.equipped);self.assertTrue(held.data['on_ground']);self.assertTrue(computed(self.b)['unarmed'])
        self.assertEqual(self.a.runtime['actions']['main'],0);self.assertEqual(self.b.runtime['hp'],10)
        self.post(self.alice,{'op':'undo'});held.refresh_from_db();self.b.refresh_from_db()
        self.assertTrue(held.equipped);self.assertNotIn('on_ground',held.data);self.assertFalse(computed(self.b)['unarmed'])
        self.post(self.alice,{'op':'redo'});held.refresh_from_db();self.assertFalse(held.equipped)

    def test_disarm_rejects_missing_roll_wrong_item_and_missing_capture(self):
        held,p=self.disarm_setup()
        for update in [{'roll_result':''},{'in_range':False},{'target':self.a.pk},{'item':0}]:self.post(self.alice,{**p,**update},400)
        held.refresh_from_db();self.assertTrue(held.equipped)
        self.a.items.update(equipped=False);self.post(self.alice,p,400)

    def test_disarm_miss_preserves_item_and_external_target_needs_no_monster(self):
        held,p=self.disarm_setup();self.post(self.alice,{**p,'outcome':'miss'})
        held.refresh_from_db();self.assertTrue(held.equipped)
        self.post(self.alice,{'op':'undo'})
        self.post(self.alice,{**p,'target':0,'item':0,'external_item':'Посох врага'})
        self.assertEqual(Event.objects.latest('id').inputs['disarm']['item'],'Посох врага')

    def test_disarm_splits_one_item_from_stack(self):
        held,p=self.disarm_setup();held.quantity=3;held.save();self.post(self.alice,p)
        held.refresh_from_db();self.assertEqual(held.quantity,2);self.assertFalse(held.equipped)
        dropped=self.b.items.get(data__on_ground=True,archived=False)
        self.assertEqual(dropped.quantity,1)
        self.post(self.alice,{'op':'undo'});held.refresh_from_db();dropped.refresh_from_db()
        self.assertEqual(held.quantity,3);self.assertTrue(held.equipped);self.assertTrue(dropped.archived)

    def test_disarmed_item_can_be_picked_up_and_blocks_stale_attacker_undo(self):
        held,p=self.disarm_setup();held.data['keywords']=['Лёгкое'];held.save()
        self.post(self.alice,p)
        scene=Scene.objects.latest('id');self.turn(scene,self.alice)
        self.post(self.bob,{'op':'item.equip','id':held.pk})
        held.refresh_from_db();self.b.refresh_from_db()
        self.assertTrue(held.equipped);self.assertNotIn('on_ground',held.data)
        self.assertEqual(self.b.runtime['actions']['main'],0);self.assertEqual(self.b.runtime['actions']['minor'],1)
        self.post(self.alice,{'op':'undo'},400)
        self.post(self.bob,{'op':'undo'});held.refresh_from_db();self.assertTrue(held.data['on_ground'])

    def test_normal_movement_counts_terrain_cost_and_can_be_undone(self):
        self.start()
        p={'op':'action.move','character':self.a.pk,'mode':'walk','cells':3,'cell_cost':2}
        self.post(self.alice,{**p,'cells':4},400)
        self.post(self.alice,p)
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['move'],0)
        self.assertEqual(Event.objects.latest('id').inputs['movement'],{'mode':'walk','cells':3,'cell_cost':2,'limit':3,'provokes':True})
        self.post(self.alice,{'op':'undo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['move'],1)
        self.post(self.alice,{'op':'redo'});self.a.refresh_from_db();self.assertEqual(self.a.runtime['actions']['move'],0)

    def test_step_uses_character_step_and_requires_normal_terrain(self):
        self.start()
        p={'op':'action.move','character':self.a.pk,'mode':'step','cells':1,'cell_cost':1}
        self.post(self.alice,{**p,'cell_cost':2},400);self.post(self.alice,{**p,'cells':2},400)
        self.post(self.alice,p);self.assertFalse(Event.objects.latest('id').inputs['movement']['provokes'])
        self.post(self.alice,{'op':'undo'})
        support=Entry.objects.create(kind='ability',name='Стихийная поддержка',data={'category':'active'})
        self.a.abilities.add(support);self.a.refresh_from_db();self.a.runtime['elemental_support']={'mode':'Воздух','ability':support.pk};self.a.save()
        self.post(self.alice,{**p,'cells':3});self.assertEqual(Event.objects.latest('id').inputs['movement']['limit'],3)

    def test_movement_respects_turn_conditions_and_validates_numbers(self):
        scene=self.start();p={'op':'action.move','character':self.a.pk,'mode':'walk','cells':1,'cell_cost':1}
        for update in [{'cells':True},{'cells':0},{'cells':1.5},{'cell_cost':0},{'cell_cost':True},{'mode':'teleport'}]:self.post(self.alice,{**p,**update},400)
        for status in ['Обездвижен','Сон','Страх']:
            self.a.refresh_from_db();self.a.runtime['effects']=[{'key':'blocked','name':status,'status':status,'value':1}];self.a.save()
            self.post(self.alice,p,400);self.post(self.alice,{**p,'mode':'step'},400)
        self.a.runtime['effects']=[];self.a.save();self.turn(scene,self.alice);self.post(self.alice,p,400)

    def test_movement_triggers_hyperthermia_once_and_never_changes_hp(self):
        self.hyperthermia_setup()
        self.post(self.alice,{'op':'action.move','character':self.a.pk,'mode':'walk','cells':6,'cell_cost':1})
        self.assertEqual([e['damage'] for e in Event.objects.latest('id').inputs['periodic_damage']],[5])
        self.a.refresh_from_db();self.assertEqual(self.a.runtime['hp'],10)

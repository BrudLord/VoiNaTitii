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

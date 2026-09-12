import copy
from django.conf import settings
from django.test import SimpleTestCase
from .models import Entry
from .attack_sequences import BOOK, plan, profile, validate_profile


class AttackSequencePlanTests(SimpleTestCase):
    def ability(self, name, **data):
        return Entry(name=name, data={'damage': True, **data})

    def row(self, target=1, outcome='hit', **extra):
        return {'target': target, 'outcome': outcome, 'roll_result': 'Попадание 17, урон 5', **extra}

    def test_same_target_preserves_each_physical_result_and_order(self):
        payload = {'attacks': [self.row(outcome='miss'), self.row(outcome='critical')]}
        before = copy.deepcopy(payload)
        result = plan(self.ability('Тормозящие стрелы'), payload, {1, 2})
        self.assertEqual([r['number'] for r in result['attacks']], [1, 2])
        self.assertEqual([r['outcome'] for r in result['attacks']], ['miss', 'critical'])
        self.assertEqual(result['successful_targets'], [('character', 1)])
        self.assertFalse(result['all_missed'])
        self.assertEqual(payload, before)
        result['attacks'][0]['roll_result'] = 'changed'
        self.assertEqual(payload, before)
        with self.assertRaisesMessage(ValueError, 'одну цель'):
            plan(self.ability('Тормозящие стрелы'), {'attacks': [self.row(1), self.row(2)]}, {1, 2})

    def test_distinct_external_targets_require_names_but_no_monster_database(self):
        rows = [self.row(None, external_target=name) for name in ['Гоблин слева', 'Гоблин справа', 'Шаман']]
        result = plan(self.ability('Серия выстрелов'), {'attacks': rows}, set())
        self.assertEqual(len(result['successful_targets']), 3)
        rows[2]['external_target'] = ' ГОБЛИН   слева '
        with self.assertRaisesMessage(ValueError, 'разные цели'):
            plan(self.ability('Серия выстрелов'), {'attacks': rows}, set())

    def test_area_requires_two_attacks_per_target_even_when_missed(self):
        rows = [self.row(1, 'miss'), self.row(2), self.row(1, 'miss'), self.row(2, 'critical')]
        result = plan(self.ability('Шквал ударов'), {'attacks': rows}, {1, 2})
        self.assertEqual(result['successful_targets'], [('character', 2)])
        with self.assertRaisesMessage(ValueError, 'каждого получателя'):
            plan(self.ability('Шквал ударов'), {'attacks': rows[:-1]}, {1, 2})

    def test_reliable_decision_uses_all_attack_results(self):
        result = plan(self.ability('Осколки тьмы'), {'attacks': [self.row(1, 'miss'), self.row(2, 'miss')]}, {1, 2})
        self.assertTrue(result['all_missed'])
        self.assertEqual(result['successful_targets'], [])

    def test_volley_uses_walked_cells_and_trusted_multiplier(self):
        a = self.ability('Направленный залп')
        rows = [self.row()] * 6
        result = plan(a, {'attacks': rows, 'steps': 3, 'multiplier': 99}, {1}, multiplier=2)
        self.assertEqual(len(result['attacks']), 6)
        for distance in [True, 0, 2, 6, '3']:
            with self.assertRaises(ValueError):
                plan(a, {'attacks': rows, 'steps': distance}, {1}, multiplier=2)
        with self.assertRaises(ValueError):
            plan(self.ability('Осколки тьмы'), {'attacks': rows, 'multiplier': 3}, {1})

    def test_optional_attacks_have_a_real_upper_bound(self):
        a = self.ability('Захват пространства')
        self.assertEqual(len(plan(a, {'attacks': [self.row()]}, {1})['attacks']), 1)
        with self.assertRaises(ValueError):
            plan(a, {'attacks': [self.row()] * 4}, {1})

    def test_rejects_missing_rolls_unknown_targets_and_invalid_outcomes(self):
        a = self.ability('Осколки тьмы')
        bad_rows = [self.row(7), self.row(True), self.row(outcome=[]), self.row(roll_result=' '),
                    self.row(roll_result=12), self.row(None), self.row(external_target='Другой'), None]
        for bad in bad_rows:
            with self.subTest(row=bad), self.assertRaises(ValueError):
                plan(a, {'attacks': [self.row(), bad]}, {1})
        with self.assertRaises(ValueError):
            plan(self.ability('Осколки тьмы', automatic_hit=True), {'attacks': [self.row(), self.row(outcome='miss')]}, {1})

    def test_explicit_profiles_survive_renaming_and_can_be_disabled(self):
        value = profile(self.ability('Быстрые уколы'))
        self.assertEqual(profile(self.ability('Мои уколы', attack_sequence=value)), value)
        self.assertIsNone(profile(self.ability('Быстрые уколы', attack_sequence=None)))
        for value in [[], {}, {'count': True, 'targets': 'same'}, {'count': 2, 'targets': []},
                      {'count': 2, 'minimum': 3, 'targets': 'same'}, {'count': 2, 'targets': 'any', 'one_per_step': 1}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_profile(value)

    def test_book_sources_include_every_fixed_series_profile(self):
        text = (settings.BASE_DIR / 'rules/player-book.txt').read_text()
        for name in BOOK:
            with self.subTest(name=name):
                block = text.split('##### ' + name + '\n', 1)[1].split('}}', 1)[0]
                self.assertTrue(any(word in block for word in ['атаки', 'атак', 'выстрел']), block)

    def test_book_compiler_exposes_sequences_without_hiding_unhandled_side_effects(self):
        from .book_audit import abilities
        text=(settings.BASE_DIR/'rules/player-book.txt').read_text()
        rows={name:data for name,_,data,_ in abilities(text) if name in BOOK}
        for name,spec in BOOK.items():
            self.assertEqual(rows[name]['attack_sequence'],spec)
            self.assertEqual(rows[name]['manual'],name in ['Захват пространства','Тормозящие стрелы'])

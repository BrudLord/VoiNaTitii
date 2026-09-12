from django.conf import settings
from django.test import SimpleTestCase
from .coverage import inventory


class BookInventoryTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.text=(settings.BASE_DIR/'rules/player-book.txt').read_text()
        cls.report=inventory(cls.text)

    def test_all_framed_rules_are_addressable_without_deduplicating_titles(self):
        framed=[r for r in self.report['units'] if r['kind']!='section']
        lines=self.text.splitlines();openings=[]
        for index,line in enumerate(lines):
            if line.strip() not in ['{{monster,frame','{{note','{{descriptive']:continue
            following=next((value for value in lines[index+1:] if value.strip()),'')
            if following.startswith('##### '):openings.append(index+1)
        self.assertEqual({r['source']['line'] for r in framed},set(openings))
        self.assertEqual(self.report['summary']['by_kind']['ability'],863)
        self.assertEqual(len({r['id'] for r in self.report['units']}),len(self.report['units']))
        for row in framed:
            start=self.text.splitlines()[row['source']['line']-1]
            self.assertTrue(start.startswith('{{'))

    def test_plain_combat_rules_and_source_handlers_are_included(self):
        mount=next(r for r in self.report['units'] if r['title']=='Бой верхом')
        self.assertIn('mount',mount['features'])
        held=next(r for r in self.report['units'] if r['title']=='Отложить действие')
        self.assertIn('game.readied',held['candidate_handlers'])
        reflex=next(r for r in self.report['units'] if r['title']=='Молниеносные рефлексы')
        self.assertIn('once_per_turn',reflex['features']);self.assertIn('reaction',reflex['features'])
        self.assertEqual(reflex['verification'],'needs_scenario_review')
        self.assertEqual(self.report['summary']['verified'],0)

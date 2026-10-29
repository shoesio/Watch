import json
import tempfile
import time
import unittest
from pathlib import Path
from tv_guide import GuideSync, initial_data, timestamp


class GuideTests(unittest.TestCase):
    def test_now_next_handles_gaps_and_never_calls_future_programme_current(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'guide.json'
            path.write_text(json.dumps({'channels':{
                'gap':{'updated_at':now,'programmes':[
                    {'title':'Ended','start':now-200,'end':now-100},
                    {'title':'Later','start':now+100,'end':now+200}]},
                'stale':{'updated_at':now-90000,'programmes':[
                    {'title':'Untrusted old listing','start':now-100,'end':now+100}]},
                'current':{'updated_at':now,'programmes':[
                    {'title':'On air','start':now-100,'end':now+100},
                    {'title':'Next','start':now+100,'end':now+200}]}}}))
            result = GuideSync(path).now_next()
            self.assertIsNone(result['gap']['now'])
            self.assertEqual(result['gap']['next']['title'], 'Later')
            self.assertNotIn('stale', result)
            self.assertEqual(result['current']['now']['title'], 'On air')
            self.assertEqual(result['current']['next']['title'], 'Next')

    def test_channel4_page_parser_ignores_following_javascript(self):
        data = initial_data('<script>var initialData = {"channels":{"C4":{"label":"A } title"}}}; alert("not data");</script>')
        self.assertEqual(data['channels']['C4']['label'], 'A } title')

    def test_schedule_offsets_refer_to_same_instant_across_clock_change(self):
        self.assertEqual(timestamp('2026-10-25T01:30:00+01:00'), timestamp('2026-10-25T00:30:00Z'))


if __name__ == '__main__':
    unittest.main()

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).parents[1] / 'server/rabbit_chat.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class BridgeTests(unittest.TestCase):
    def test_payload_and_reasoning_boundary(self):
        request = bridge.payload({'locale':'zh','context':{'stage':'Pilot'},'messages':[{'role':'user','content':'你好'}]})
        self.assertEqual(request['thinking'],{'type':'disabled'})
        self.assertTrue(request['stream'])
        self.assertNotIn('tools',request)
        self.assertIn('DEMO',request['messages'][0]['content'])
        self.assertIn('Doudou (豆豆)',request['messages'][0]['content'])
        lines = [b'data: '+json.dumps({'choices':[{'delta':{'reasoning_content':'PRIVATE','content':'hello'}}]}).encode(), b'data: [DONE]']
        events=list(bridge.content_events(lines))
        self.assertEqual(events,[{'type':'delta','text':'hello'},{'type':'done'}])
        self.assertNotIn('PRIVATE',json.dumps(events))

    def test_truncated_stream_and_length_limit_are_not_success(self):
        self.assertEqual(list(bridge.content_events([])),[{'type':'error','code':'interrupted'}])
        line=b'data: '+json.dumps({'choices':[{'delta':{},'finish_reason':'length'}]}).encode()
        self.assertEqual(list(bridge.content_events([line]))[-1]['type'],'error')

    def test_private_env_is_read_as_data_not_executed(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            path=Path(directory)/'.env.local'
            path.write_text("export DEEPSEEK_API_KEY='fake-literal-$(do-not-run)'\n")
            self.assertEqual(bridge.api_key(path),'fake-literal-$(do-not-run)')

    def test_followups_are_separate_from_streamed_answer_at_every_split(self):
        answer = '豆豆来解释一下：VHH 是单域抗体。🐰\n'
        questions = ['VHH 和普通抗体有什么区别？', 'VHH 可以用在哪些研究中？']
        text = answer + bridge.FOLLOWUP_MARKER + json.dumps(questions, ensure_ascii=False)
        splits = [[text[:i], text[i:]] for i in range(len(text) + 1)] + [list(text)]
        for parts in splits:
            events = [{'type':'delta','text':part} for part in parts] + [{'type':'done'}]
            result = list(bridge.reply_events(events, 'zh'))
            self.assertEqual(''.join(e['text'] for e in result if e['type']=='delta'), answer)
            self.assertEqual(result[-2], {'type':'suggestions', 'questions':questions})
            self.assertEqual(result[-1], {'type':'done'})

    def test_followup_validation_fallback_and_cancellation(self):
        self.assertEqual(bridge.questions_from_footer('["问题？","问题？",null,"",123,"另一个问题？"]', 'zh'),
                         ['问题？', '另一个问题？'])
        self.assertEqual(len(bridge.questions_from_footer('["a","b","c","d"]', 'en')), 3)
        for footer in ['["A?","B?"]</doudou_questions>', '```json\n["A?","B?"]\n```']:
            self.assertEqual(bridge.questions_from_footer(footer, 'en'), ['A?', 'B?'])
        for footer in ['invalid', '{}', '[null]', '["' + 'a' * 121 + '"]']:
            self.assertEqual(len(bridge.questions_from_footer(footer, 'en')), 2)
        events = [{'type':'delta','text':'Plain answer <'}, {'type':'done'}]
        result = list(bridge.reply_events(events, 'en'))
        self.assertEqual(''.join(e['text'] for e in result if e['type']=='delta'), 'Plain answer <')
        self.assertEqual(result[-2]['type'], 'suggestions')
        interrupted = [{'type':'delta','text':'Partial answer' + bridge.FOLLOWUP_MARKER + '["partial'},
                       {'type':'error','code':'interrupted'}]
        result = list(bridge.reply_events(interrupted, 'zh'))
        self.assertFalse(any(e['type']=='suggestions' for e in result))
        self.assertEqual(result[-1]['type'], 'error')

if __name__ == '__main__':
    unittest.main()

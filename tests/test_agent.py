import unittest
from src.agent import run

class AgentTests(unittest.TestCase):
    def test_clear(self):
        r=run({'question':'年假如何申请'})
        self.assertEqual(r['status'],'completed')
        self.assertEqual(r['citations'][0]['doc_id'],'D03')
    def test_conflict(self):
        r=run({'question':'报销期限多久'})
        self.assertEqual(r['status'],'conflict')
        self.assertEqual(len(r['citations']),2)
    def test_outside(self):
        r=run({'question':'火星天气如何'})
        self.assertEqual(r['status'],'insufficient_evidence')
        self.assertEqual(sum(t['action']=='search' for t in r['trace']),2)
    def test_paraphrase(self):
        self.assertEqual(run({'question':'费用最晚几天提交'})['status'],'conflict')
    def test_context(self):
        self.assertEqual(run({'question':'需要提前多久？','history':['我想申请年假']})['citations'][0]['doc_id'],'D03')
    def test_failure(self):
        self.assertEqual(run({'question':'报销','simulate_tool_failure':True})['status'],'tool_error')
    def test_limit(self):
        self.assertEqual(run({'question':'报销','max_steps':1})['status'],'incomplete')
    def test_replaced_documents(self):
        docs=[dict(id='D01',version_date='2026-10-01',title='新制度',text='报销期限为45天。',keywords=['报销'])]
        r=run({'question':'报销'},documents=docs)
        self.assertEqual(r['status'],'completed')
        self.assertIn('45天',r['answer'])
        self.assertEqual(r['trace'][1]['parameters']['ids'],['D01'])
    def test_fabricated_quote(self):
        def fake(messages):
            return dict(action='finish',result=dict(status='completed',answer='15天',citations=[dict(doc_id='D02',quote='伪造',version_date='2026-02-01')],gaps=[]))
        self.assertEqual(run({'question':'报销'},policy=fake)['status'],'invalid_evidence')
    def test_invalid(self):
        for req in ({},{'question':'报销','max_steps':True},{'question':'报销','history':'错误'}):
            with self.assertRaises(ValueError):run(req)

if __name__=='__main__':unittest.main()

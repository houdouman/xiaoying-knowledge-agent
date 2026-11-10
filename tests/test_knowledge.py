import unittest
from src.knowledge import split_documents, search
from src.agent import run, parse_action


class KnowledgeTests(unittest.TestCase):
    def test_multiple_tool_proposals_execute_first_only(self):
        self.assertEqual(parse_action('{"action":"read","ids":["X"]}\n{"action":"search","query":"范围"}')['action'],'read')
        with self.assertRaises(ValueError):parse_action('{"action":"read"}\n{"action":"finish"}')

    def test_offsets_reconstruct_source(self):
        text='年假须提前申请。'*80
        chunks=split_documents([dict(id='X',title='年假',version_date='2026-01-01',text=text,keywords=['年假'])])
        self.assertGreater(len(chunks),1)
        self.assertEqual(''.join(c['text'] for c in chunks),text)
        for c in chunks:self.assertEqual(c['text'],text[c['start']:c['end']])

    def test_body_retrieval_without_curated_keywords(self):
        chunks=split_documents([dict(id='X',title='制度',version_date='2026-01-01',text='远程办公申请由部门经理审批。',keywords=[])])
        self.assertEqual(search(chunks,'远程办公申请流程')[0]['id'],'X')
        self.assertEqual(search(chunks,'火星天气'),[])

    def test_unread_chunk_cannot_be_cited(self):
        docs=[dict(id='X',title='制度',version_date='2026-01-01',text='甲'*240+'乙'*50,keywords=['制度'])]
        def policy(messages):
            if len(messages)==1:return dict(action='read',ids=['X:0-240'])
            return dict(action='finish',result=dict(status='completed',answer='乙乙',citations=[dict(doc_id='X',version_date='2026-01-01',quote='乙乙')],gaps=[]))
        self.assertEqual(run({'question':'制度'},documents=docs,policy=policy)['status'],'invalid_evidence')

    def test_citation_offsets(self):
        result=run({'question':'年假'})
        c=result['citations'][0]
        self.assertIn('chunk_id',c)
        self.assertEqual(c['end']-c['start'],len(c['quote']))

    def test_live_validation_feedback_repairs_unread_quote(self):
        doc=dict(id='X',title='制度',version_date='2026-01-01',text='请提前申请。',keywords=['制度'])
        def policy(messages):
            result=dict(status='completed',answer=doc['text'],citations=[dict(doc_id='X',version_date=doc['version_date'],quote=doc['text'])],gaps=[])
            if not any(m.get('validation_error') for m in messages):
                return dict(action='finish',result=result)
            if not any('observation' in m for m in messages):
                return dict(action='read',ids=['X'])
            return dict(action='finish',result=result)
        r=run({'question':'制度'},mode='live',documents=[doc],policy=policy)
        self.assertEqual(r['status'],'completed')
        self.assertEqual([t['action'] for t in r['trace']],['finish','read','finish'])
        self.assertIn('validation_error',r['trace'][0])

"""Reproducible acceptance checks. Live evaluation incurs provider API calls."""
import argparse
import json
from pathlib import Path
from .agent import ROOT, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['live','offline'], default='offline')
    args = parser.parse_args()
    output = ROOT/'examples'/f'acceptance-{args.mode}'
    output.mkdir(exist_ok=True)
    docs = json.loads((ROOT/'data/documents.json').read_text(encoding='utf-8'))
    cases = [
        ('normal', {'question':'年假如何申请'}, docs, 'completed', ['D03'], '3个工作日'),
        ('conflict', {'question':'报销期限多久'}, docs, 'conflict', ['D01','D02'], '30'),
        ('missing', {'question':'火星天气如何'}, docs, 'insufficient_evidence', [], ''),
        ('paraphrase', {'question':'垫付的钱最晚什么时候能找公司结算？'}, docs, 'conflict', ['D01','D02'], '15'),
        ('context', {'question':'需要提前多久？','history':['我想申请年假']}, docs, 'completed', ['D03'], '3个工作日'),
        ('tool-failure', {'question':'报销期限','simulate_tool_failure':True}, docs, 'tool_error', [], ''),
        ('single-source', {'question':'报销期限多久'}, [docs[0]], 'completed', ['D01'], '30'),
        ('replacement', {'question':'报销期限多久'}, [dict(docs[0],text='员工应在费用发生后45天内提交报销申请。')], 'completed', ['D01'], '45'),
        ('resolved', {'question':'报销期限多久'}, docs + [dict(id='D04',title='报销制度适用说明',version_date='2026-04-01',keywords=['优先级','适用','替代'],text='D02已废止，所有员工费用报销统一适用D01的30天期限。')], 'completed', ['D01','D04'], '30'),
    ]
    summary=[]
    for name, request, corpus, status, ids, phrase in cases:
        result=run(request,args.mode,documents=corpus)
        cited={c['doc_id'] for c in result['citations']}
        checks={'status':result['status']==status,'sources':set(ids)<=cited,
                'answer':phrase in result['answer']}
        if name in ('conflict','paraphrase'):
            checks['both_values']=all(value in result['answer'] for value in ('30','15'))
            checks['asks_clarification']=any(word in result['answer'] for word in ('确认','请问','提供'))
        if name=='replacement':
            checks['no_old_value']='30天' not in result['answer'] and '15天' not in result['answer']
        if name=='conflict' and args.mode=='live':
            first_read=next((i for i,t in enumerate(result['trace']) if t['action']=='read'),len(result['trace']))
            checks['conflict_investigation']=any(t['action']=='search' for t in result['trace'][first_read+1:])
        (output/f'{name}.json').write_text(json.dumps(dict(request=request,documents=corpus,result=result,checks=checks),ensure_ascii=False,indent=2),encoding='utf-8')
        row=dict(case=name,status=result['status'],passed=all(checks.values()),checks=checks,**result['metrics'])
        summary.append(row)
        print(json.dumps(row),flush=True)
        (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(row['passed'] for row in summary) else 1

if __name__=='__main__':raise SystemExit(main())

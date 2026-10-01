from backend.collectors.betshoot import parse_html

def test_public_row():
    html='''<html><body><div>Real Betis - AD Ceuta</div><span>1.50</span><span>1.38</span><span>4.50</span><span>4.75</span><span>4.50</span><span>5.75</span><span>1.44</span><span>1.44</span><span>2.63</span><span>2.63</span><span>1.57</span><span>1.67</span></body></html>'''
    rows=parse_html(html)
    assert len(rows)==1
    assert rows[0]['home']=='Real Betis'
    assert 'BETSHOOT_DROP_1_8.0%' in rows[0]['signals']

if __name__=='__main__':
    test_public_row(); print('Betshoot parser: OK')

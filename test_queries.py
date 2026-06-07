
import sqlite3, sys
sys.path.insert(0, '.')
conn = sqlite3.connect('sansad.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

print('=== TOTAL MPs ===')
c.execute('SELECT COUNT(*) FROM members')
print('Members:', c.fetchone()[0])

print('\n=== TOP 15 BY STATEMENTS ===')
c.execute('''SELECT m.name, m.party, COUNT(s.id) as cnt
             FROM members m JOIN statements s ON s.member_id=m.id
             GROUP BY m.id ORDER BY cnt DESC LIMIT 15''')
for r in c.fetchall():
    print(f'  {r[\"name\"]:<45} {r[\"party\"] or \"?\":<12} {r[\"cnt\"]:>4}')

print('\n=== BY PARTY ===')
c.execute('''SELECT COALESCE(m.party,\"Unknown\") as p,
             COUNT(DISTINCT m.id) as members, COUNT(s.id) as stmts
             FROM members m LEFT JOIN statements s ON s.member_id=m.id
             GROUP BY p ORDER BY stmts DESC''')
for r in c.fetchall():
    print(f'  {r[\"p\"]:<22} {r[\"members\"]:>3} MPs   {r[\"stmts\"]:>5} stmts')

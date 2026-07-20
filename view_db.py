import sqlite3

conn = sqlite3.connect("database/history.db")

cursor = conn.cursor()

cursor.execute("SELECT * FROM downloads")

rows = cursor.fetchall()

for row in rows:
    print(row)

conn.close()
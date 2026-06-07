from core.db import get_connection, sync_db
c = get_connection()
c.execute("UPDATE source_pdfs SET parse_status='pending'")
c.commit()
sync_db()
print('All PDFs queued')
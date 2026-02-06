from controllers.database import connect, init_db, add_song
from controllers.match import recognize

conn = connect(":memory:")
init_db(conn)
#add_song(conn, "test_song", fps)

# results = recognize(conn, fps)
# print("Recognition results:", results)

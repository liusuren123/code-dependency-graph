import sqlite3

conn = sqlite3.connect('data/dependency.db')
cursor = conn.cursor()

# 查找 SimpleColorControlProc 的 ID
cursor.execute("""
    SELECT id, name, file_path, line_number FROM symbols
    WHERE name = 'SimpleColorControlProc' AND file_path LIKE '%ColorControl.cpp'
""")
proc_rows = cursor.fetchall()
print("SimpleColorControlProc symbols in ColorControl.cpp:")
for row in proc_rows:
    print(f"  id={row[0]}, name={row[1]}, file={row[2]}, line={row[3]}")

# 查找 SimpleColorDoPaint 的 ID
cursor.execute("""
    SELECT id, name, file_path, line_number FROM symbols
    WHERE name = 'SimpleColorDoPaint' AND file_path LIKE '%ColorControl.cpp'
""")
paint_rows = cursor.fetchall()
print("\nSimpleColorDoPaint symbols in ColorControl.cpp:")
for row in paint_rows:
    print(f"  id={row[0]}, name={row[1]}, file={row[2]}, line={row[3]}")

# 查找这两个符号之间的依赖关系
if proc_rows and paint_rows:
    proc_id = proc_rows[0][0]
    paint_id = paint_rows[0][0]

    print(f"\nChecking dependency: SimpleColorControlProc(id={proc_id}) -> SimpleColorDoPaint(id={paint_id})")

    cursor.execute("""
        SELECT * FROM dependencies
        WHERE source_symbol_id = ? AND target_symbol_id = ?
    """, (proc_id, paint_id))
    deps = cursor.fetchall()

    if deps:
        print(f"  Found {len(deps)} dependency records")
        for d in deps:
            print(f"    {d}")
    else:
        print("  No direct dependency found")

    # 查找所有从 SimpleColorControlProc 出发的 calls 依赖
    cursor.execute("""
        SELECT d.*, s.name as target_name FROM dependencies d
        LEFT JOIN symbols s ON d.target_symbol_id = s.id
        WHERE d.source_symbol_id = ? AND d.dependency_type = 'calls'
    """, (proc_id,))
    outgoing_calls = cursor.fetchall()
    print(f"\nAll outgoing 'calls' from SimpleColorControlProc:")
    for row in outgoing_calls:
        print(f"  {row}")

conn.close()
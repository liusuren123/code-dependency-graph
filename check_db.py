import sqlite3

conn = sqlite3.connect('data/dependency.db')
cursor = conn.cursor()

# 查看表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:", tables)

# 检查 symbols 表中是否有 SimpleColor 相关符号
cursor.execute("SELECT name, file_path, kind FROM symbols WHERE name LIKE '%SimpleColor%' OR name = 'SimpleColorDoPaint'")
symbols = cursor.fetchall()
print("\nSymbols matching 'SimpleColor':")
for s in symbols:
    print(f"  {s}")

# 检查 dependencies 表
cursor.execute("SELECT COUNT(*) FROM dependencies")
print(f"\nTotal dependencies: {cursor.fetchone()[0]}")

# 检查是否有 calls 类型的依赖
cursor.execute("SELECT COUNT(*) FROM dependencies WHERE dependency_type = 'calls'")
print(f"Calls dependencies: {cursor.fetchone()[0]}")

# 查看数据库路径
cursor.execute("PRAGMA database_list")
print("\nDatabase files:")
for row in cursor.fetchall():
    print(f"  {row}")

conn.close()
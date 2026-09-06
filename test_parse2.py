import re

def _extract_imported_symbols(stmt: str):
    # Membersihkan keyword import, export, from, type
    stmt = re.sub(r'\b(?:import|export|from|type)\b', '', stmt)
    
    symbols = []
    
    # 1. Cari named imports dalam { }
    named_match = re.search(r'\{([^}]+)\}', stmt)
    if named_match:
        named_str = named_match.group(1)
        for s in named_str.split(','):
            s = s.strip()
            if not s: continue
            if ' as ' in s:
                symbols.append(s.split(' as ')[1].strip())
            else:
                symbols.append(s)
        # Hapus bagian {...} dari stmt agar sisa default import gampang diambil
        stmt = stmt.replace('{' + named_str + '}', '')
    
    # 2. Cari default / namespace imports
    stmt = stmt.strip()
    if stmt:
        for s in stmt.split(','):
            s = s.strip()
            if not s: continue
            if s.startswith('* as '):
                symbols.append(s[5:].strip())
            elif '*' not in s:
                symbols.append(s)
                
    return symbols

print(_extract_imported_symbols("import { Injectable, Optional } from "))
print(_extract_imported_symbols("import { UserService } from "))
print(_extract_imported_symbols("import defaultAlias, { Component as Comp } from "))
print(_extract_imported_symbols("import * as utils from "))
print(_extract_imported_symbols("import type { Admin } from "))

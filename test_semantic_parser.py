import re

IMPORT_STMT = re.compile(
    r"(?:import|export)\s+(?:type\s+)?(?:(?P<default>[A-Za-z0-9_]+)\s*,?\s*)?(?:\{(?P<named>[^}]+)\})?\s*from\s*['\"](?P<path>[^'\"]+)['\"]"
)

content = """
import { Injectable, Optional } from '@angular/core';
import { UserService } from './user.service';
import defaultAlias, { Component as Comp } from './my-comp';

@Injectable()
export class MyClass {
    constructor(private user: UserService) {}

    init() {
        this.user.load();
        Comp();
        defaultAlias();
        const x = new UserService();
    }
}
"""

def extract_semantic_relations(content):
    imported_symbols = {}
    for match in IMPORT_STMT.finditer(content):
        path = match.group('path')
        symbols = []
        if match.group('default'):
            symbols.append(match.group('default').strip())
        if match.group('named'):
            for s in match.group('named').split(','):
                s = s.strip()
                if not s: continue
                if ' as ' in s:
                    symbols.append(s.split(' as ')[1].strip())
                else:
                    symbols.append(s)
        
        if path not in imported_symbols:
            imported_symbols[path] = []
        imported_symbols[path].extend(symbols)
    
    relations = {}
    for path, symbols in imported_symbols.items():
        used_as = []
        for sym in symbols:
            if re.search(rf"\bnew\s+{sym}\b", content):
                used_as.append(f"instantiated({sym})")
            elif re.search(rf"\b{sym}\s*\(", content):
                if re.search(rf"@{sym}\b", content):
                    used_as.append(f"decorator({sym})")
                else:
                    used_as.append(f"called({sym})")
            elif re.search(rf":\s*{sym}\b", content):
                used_as.append(f"typed({sym})")
            elif re.search(rf"<{sym}\b", content):
                used_as.append(f"jsx_component({sym})")
        if used_as:
            relations[path] = used_as
            
    return relations

print(extract_semantic_relations(content))

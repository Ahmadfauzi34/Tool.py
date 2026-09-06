import re

def _find_semantic_usages(symbols, content):
    usages = []
    for sym in symbols:
        # Prevent regex errors if symbol is weird
        if not re.match(r'^[A-Za-z0-9_]+$', sym):
            continue
            
        if re.search(rf"\bnew\s+{sym}\b", content):
            usages.append(f"instantiated({sym})")
        elif re.search(rf"\b{sym}\s*\(", content):
            if re.search(rf"@{sym}\b", content):
                usages.append(f"decorator({sym})")
            else:
                usages.append(f"called({sym})")
        elif re.search(rf":\s*{sym}\b", content) or re.search(rf":\s*Promise<{sym}>", content) or re.search(rf":\s*Observable<{sym}>", content) or re.search(rf"<{sym}>", content):
            usages.append(f"typed({sym})")
        elif re.search(rf"<{sym}\b", content):
            usages.append(f"jsx_component({sym})")
        elif re.search(rf"\bextends\s+{sym}\b|\bimplements\s+{sym}\b", content):
            usages.append(f"inherited({sym})")
        elif re.search(rf"\b{sym}\.", content):
            usages.append(f"namespace_access({sym})")
            
    return list(set(usages))

content = """
import { Injectable, Optional } from '@angular/core';
import { UserService, UserData } from './user.service';
import defaultAlias, { Component as Comp } from './my-comp';

@Injectable()
export class MyClass extends Base {
    user!: UserData;
    constructor(private userSvc: UserService) {}

    init() {
        this.userSvc.load();
        Comp();
        defaultAlias.doSomething();
        const x = new UserService();
    }
}
"""

symbols = ['Injectable', 'UserService', 'UserData', 'Comp', 'defaultAlias']
print(_find_semantic_usages(symbols, content))

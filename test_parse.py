import re

IMPORT_STATEMENT_REGEX = re.compile(
    r"""(?:(?P<stmt>(?:import|export)\s+(?:[^"';]*?\bfrom\s+)?|import\s*\(\s*))["'](?P<path>[^"']+)["']""",
    re.MULTILINE,
)

content = """
import { Injectable, Optional } from '@angular/core';
import { UserService } from './user.service';
import defaultAlias, { Component as Comp } from './my-comp';
"""

for match in IMPORT_STATEMENT_REGEX.finditer(content):
    print("Stmt:", match.group('stmt'))
    print("Path:", match.group('path'))

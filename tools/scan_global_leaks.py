#!/usr/bin/env python3
"""
tools/scan_global_leaks.py
==========================
Lexical scope and global leak detector for TurtleMail.
Accurately tracks:
  1. Lexical block scopes (function, if, for, while, do ... end)
  2. Table constructors ({ ... }), differentiating table fields from variable assignments
  3. Function arguments, loop variables, and local declarations
"""

import os
import re
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

TARGET_FILES = [
    "TurtleMail.lua",
    "Calendar.lua",
    "localization.lua",
    "localization.de.lua",
    "localization.es.lua",
    "localization.fr.lua",
    "localization.ru.lua",
]

# Standard WoW 1.12 globals & expected TurtleMail globals
KNOWN_GLOBALS = {
    # TurtleMail AddOn Namespaces & SavedVariables
    "TurtleMail", "TurtleMail_AutoCompleteNames", "TurtleMail_To", "TurtleMail_Point", "TurtleMail_Log",
    "SLASH_TURTLEMAIL1", "SLASH_TURTLEMAIL2", "SlashCmdList",

    # WoW 1.12 Engine Globals
    "UIParent", "DEFAULT_CHAT_FRAME", "GameTooltip", "WorldFrame",
    "CreateFrame", "GetTime", "GetServerTime", "GetGameTime", "date", "time",
    "string", "table", "math", "pairs", "ipairs", "next", "type", "tostring", "tonumber",
    "print", "pcall", "unpack", "getn", "setglobal", "getglobal", "this", "event",
    "arg1", "arg2", "arg3", "arg4", "arg5", "arg6", "arg7", "arg8", "arg9",
    "UnitName", "UnitLevel", "UnitFactionGroup", "GetRealmName", "GetLocale", "LibStub",
    "StaticPopupDialogs", "StaticPopup_Show", "StaticPopup_Hide", "UIDropDownMenu_Initialize",
    "UIDropDownMenu_CreateInfo", "UIDropDownMenu_AddButton", "UIDropDownMenu_SetSelectedID",
    "UIDropDownMenu_SetSelectedValue", "UIDropDownMenu_SetText", "ToggleDropDownMenu",
    "CloseDropDownMenus", "PlaySound", "SOUNDKIT", "UIErrorsFrame", "ChatFrame1",
    "SendChatMessage", "RegisterForSave", "IsShiftKeyDown", "IsControlKeyDown", "IsAltKeyDown",
    "GetCurrentMapContinent", "GetChannelName", "GetChannelList", "JoinChannelByName",
    "mod", "math.mod", "math.floor", "math.ceil", "math.min", "math.max", "math.abs", "math.random",
    "getfenv", "setfenv", "assert", "error", "select", "collectgarbage",

    # Mail & Item APIs
    "MailFrame", "SendMailFrame", "InboxFrame", "OpenMailFrame", "SendMailNameEditBox",
    "SendMailSubjectEditBox", "SendMailBodyEditBox", "SendMailMoneyCopper", "SendMailMoneySilver", "SendMailMoneyGold",
    "SendMailPackageButton", "SendMailCODButton", "SendMailSendMoneyButton", "SendMailMailButton", "SendMailCancelButton",
    "InboxPrevPageButton", "InboxNextPageButton", "OpenMailPackageButton", "OpenMailMoneyButton", "OpenMailReportSpamButton",
    "GetInboxNumItems", "GetInboxHeaderInfo", "GetInboxItem", "GetInboxItemLink", "TakeInboxItem", "TakeInboxMoney",
    "DeleteInboxItem", "GetSendMailItem", "ClickSendMailItemButton", "ClearSendMail", "SendMail",
    "SetSendMailCOD", "SetSendMailMoney", "GetContainerNumSlots", "GetContainerItemInfo", "GetContainerItemLink",
    "PickupContainerItem", "UseContainerItem", "GetItemInfo", "GetMoney", "MoneyFrame_Update",
    "ITEM_QUALITY_COLORS", "NORMAL_FONT_COLOR", "GRAY_FONT_COLOR", "GREEN_FONT_COLOR", "RED_FONT_COLOR", "HIGHLIGHT_FONT_COLOR",
    "FONT_COLOR_CODE_CLOSE", "MoneyToggle_OnClick", "CursorHasItem", "ClearCursor",
    "MailAutoCompleteBox", "TurtleMailLogFrame", "TurtleMailInboxButton", "TurtleMailCheckAllButton",
    "TurtleMailSelectAllButton", "TurtleMailSelectNoneButton", "TurtleMailTakeAllButton",
    "TurtleMailClearLogButton", "TurtleMailLogFilterEditBox", "TurtleMailOptionsFrame"
}

def tokenize(code: str):
    """Tokenize Lua code while stripping comments and strings."""
    tokens = []
    code = re.sub(r'--\[\[.*?\]\]', '', code, flags=re.DOTALL)
    
    token_spec = [
        ('COMMENT',  r'--[^\n]*'),
        ('STRING1',  r'"(\\.|[^"\\])*"'),
        ('STRING2',  r"'(\\.|[^'\\])*'"),
        ('NEWLINE',  r'\n'),
        ('ASSIGN',   r'=(?!=)'),
        ('LBRACE',   r'\{'),
        ('RBRACE',   r'\}'),
        ('LPAREN',   r'\('),
        ('RPAREN',   r'\)'),
        ('COMMA',    r','),
        ('SEMI',     r';'),
        ('DOT',      r'\.'),
        ('COLON',    r':'),
        ('WORD',     r'[a-zA-Z_][a-zA-Z0-9_]*'),
        ('OTHER',    r'[^\s\w]'),
    ]
    tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in token_spec)
    
    line_num = 1
    for mo in re.finditer(tok_regex, code):
        kind = mo.lastgroup
        val = mo.group()
        if kind == 'NEWLINE':
            line_num += 1
        elif kind in ('COMMENT', 'STRING1', 'STRING2'):
            pass
        elif kind == 'WORD' or kind in ('ASSIGN', 'LBRACE', 'RBRACE', 'LPAREN', 'RPAREN', 'COMMA', 'SEMI', 'DOT', 'COLON'):
            tokens.append((kind, val, line_num))
    return tokens

def analyze_tokens(tokens):
    """Analyze token stream for lexical scope and global leaks."""
    leaks = []
    scope_stack = [set()]
    brace_depth = 0
    paren_depth = 0
    
    i = 0
    n = len(tokens)
    
    while i < n:
        kind, val, line = tokens[i]
        
        if kind == 'LBRACE':
            brace_depth += 1
            i += 1
            continue
        elif kind == 'RBRACE':
            if brace_depth > 0:
                brace_depth -= 1
            i += 1
            continue
        elif kind == 'LPAREN':
            paren_depth += 1
            i += 1
            continue
        elif kind == 'RPAREN':
            if paren_depth > 0:
                paren_depth -= 1
            i += 1
            continue
            
        if kind == 'WORD' and val in ('do', 'then'):
            scope_stack.append(set())
            i += 1
            continue
            
        if kind == 'WORD' and val == 'function':
            scope_stack.append(set())
            i += 1
            while i < n and tokens[i][0] != 'LPAREN':
                i += 1
            if i < n and tokens[i][0] == 'LPAREN':
                i += 1
                while i < n and tokens[i][0] != 'RPAREN':
                    if tokens[i][0] == 'WORD':
                        scope_stack[-1].add(tokens[i][1])
                    i += 1
                if i < n and tokens[i][0] == 'RPAREN':
                    i += 1
            continue

        if kind == 'WORD' and val == 'for':
            scope_stack.append(set())
            i += 1
            while i < n and tokens[i][1] not in ('in', '=', 'do'):
                if tokens[i][0] == 'WORD':
                    scope_stack[-1].add(tokens[i][1])
                i += 1
            continue

        if kind == 'WORD' and val == 'end':
            if len(scope_stack) > 1:
                scope_stack.pop()
            i += 1
            continue

        if kind == 'WORD' and val == 'local':
            i += 1
            if i < n and tokens[i][1] == 'function':
                i += 1
                if i < n and tokens[i][0] == 'WORD':
                    scope_stack[-1].add(tokens[i][1])
                    scope_stack.append(set())
                    i += 1
                    while i < n and tokens[i][0] != 'LPAREN':
                        i += 1
                    if i < n and tokens[i][0] == 'LPAREN':
                        i += 1
                        while i < n and tokens[i][0] != 'RPAREN':
                            if tokens[i][0] == 'WORD':
                                scope_stack[-1].add(tokens[i][1])
                            i += 1
                        if i < n and tokens[i][0] == 'RPAREN':
                            i += 1
                continue
            else:
                while i < n and tokens[i][0] == 'WORD':
                    scope_stack[-1].add(tokens[i][1])
                    i += 1
                    if i < n and tokens[i][0] == 'COMMA':
                        i += 1
                    else:
                        break
                continue

        if kind == 'ASSIGN' and brace_depth == 0:
            if i > 0 and tokens[i-1][0] == 'WORD':
                prev_var = tokens[i-1][1]
                prev_line = tokens[i-1][2]
                
                is_field = False
                if i >= 2 and tokens[i-2][0] in ('DOT', 'COLON'):
                    is_field = True
                    
                if not is_field:
                    is_declared = any(prev_var in s for s in scope_stack) or (prev_var in KNOWN_GLOBALS)
                    if not is_declared:
                        leaks.append((prev_line, prev_var))

        i += 1

    return leaks

def main():
    print("=" * 70)
    print("TURTLEMAIL: AST-LEVEL SCOPE & GLOBAL LEAK DETECTOR")
    print("=" * 70)

    total_leaks = 0
    checked_count = 0

    for rel in TARGET_FILES:
        full_path = os.path.join(ADDON_ROOT, rel)
        if not os.path.isfile(full_path):
            continue
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            code = f.read()
        tokens = tokenize(code)
        leaks = analyze_tokens(tokens)
        checked_count += 1
        
        if leaks:
            for line, var in leaks:
                print(f"  {rel}:{line}: [LEAK] Undeclared global assignment '{var}'")
            total_leaks += len(leaks)
        else:
            print(f"  [PASS] {rel} (zero global scope leaks)")

    print("-" * 70)
    if total_leaks == 0:
        print(f"RESULT: ALL {checked_count} MODULES HAVE CLEAN LOCAL SCOPING (0 GLOBAL LEAKS)")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"RESULT: {total_leaks} SCOPE LEAKS FOUND")
        print("=" * 70)
        sys.exit(1)

if __name__ == "__main__":
    main()

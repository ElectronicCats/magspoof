"""Parser/serializador minimo de S-expressions de KiCad (sin dependencias)."""
import re

class Sym(str):
    """Atomo sin comillas."""
    pass

_tok = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')

def parse(text):
    pos = 0
    stack = [[]]
    n = len(text)
    while pos < n:
        m = _tok.match(text, pos)
        if not m:
            break
        pos = m.end()
        if m.group(1):
            new = []
            stack[-1].append(new)
            stack.append(new)
        elif m.group(2):
            stack.pop()
        elif m.group(3) is not None:
            s = m.group(3)
            s = s.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            stack[-1].append(s)
        else:
            stack[-1].append(Sym(m.group(4)))
    return stack[0][0]

def q(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'

def dump(node, ind=0):
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, str):
        return q(node)
    if isinstance(node, (int,)):
        return str(node)
    if isinstance(node, float):
        s = ('%.4f' % node).rstrip('0').rstrip('.')
        return s if s not in ('-0', '') else '0'
    # lista
    simple = all(not isinstance(c, list) for c in node)
    if simple:
        return '(' + ' '.join(dump(c) for c in node) + ')'
    out = ['(' + dump(node[0])]
    i = 1
    while i < len(node) and not isinstance(node[i], list):
        out[0] += ' ' + dump(node[i])
        i += 1
    for c in node[i:]:
        out.append('\t' * (ind + 1) + dump(c, ind + 1))
    out.append('\t' * ind + ')')
    return '\n'.join(out)

def find(node, key):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]

def find1(node, key):
    r = find(node, key)
    return r[0] if r else None

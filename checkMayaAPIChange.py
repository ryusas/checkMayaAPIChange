# coding: utf-8
u"""
Find out the differences between Maya API versions.
"""
import os
import sys
import re
import subprocess

INSTALL_DIR_FORMATS = (
    'C:/Program Files/Autodesk/Maya%s',
)
VERSION_BEGIN = 2012

_os_path_isdir = os.path.isdir
_os_path_exists = os.path.exists
_os_path_dirname = os.path.dirname
_os_path_split = os.path.split
_os_path_splitext = os.path.splitext
_os_path_join = os.path.join
_os_makedirs = os.makedirs


#------------------------------------------------------------------------------
def _findMayaDirs():
    def finddir(sver):
        for fmt in INSTALL_DIR_FORMATS:
            dir = fmt % sver
            if _os_path_isdir(dir):
                return dir

    ver = VERSION_BEGIN
    notfounds = 0
    mayadirs = []
    while notfounds < 40:
        sver = str(ver)
        if sver.endswith('.0'):
            sver = sver[:-2]
        dir = finddir(sver)
        if dir:
            mayadirs.append((sver, dir))
            notfounds = 0
        else:
            notfounds += 1
        ver += .1
    return mayadirs


#------------------------------------------------------------------------------
def runcmd(cmdArgs, stdin=None, stdout=None, stderr=None):
    params = {
        'stderr': stderr or sys.stderr,  #subprocess.PIPE,
        'stdin': stdin or sys.stdin,  #subprocess.PIPE,
        'stdout': stdout or sys.stdout,  #subprocess.PIPE,
    }

    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        #params['shell'] = True
        params['startupinfo'] = si

    p = subprocess.Popen(cmdArgs, **params)
    output = p.communicate()
    returnCode = p.returncode

    if p.returncode:
        raise RuntimeError('"%s" command returned an error.' % os.path.basename(cmdArgs[0]))

    return output


def execWithArgs(name):
    args = []
    kwargs = {}
    for arg in sys.argv[1:]:
        if '=' in arg:
            k, v = arg.split('=')
            try:
                v = eval(v)
            except SyntaxError:
                pass
            if k:
                kwargs[k] = v
            else:
                cmdargs.append(v)
        else:
            try:
                v = eval(arg)
            except SyntaxError:
                v = arg
            args.append(v)
    globals()[name](*args, **kwargs)


def callSubProc(moddir, modname, funcname, mayadir, *args, **kwargs):
    runcmd(
        [
            _os_path_join(mayadir, 'bin/mayapy'),
            "-c", "import sys; sys.path.append(r'%s'); from %s import execWithArgs; execWithArgs(%r)" % (moddir, modname, funcname),
        ] + [repr(v) for v in args] + [('%s=%r' % v) for v in kwargs.items()],
        stdout=sys.stdout, stderr=sys.stderr,
    )


#------------------------------------------------------------------------------
def checkMaya(basedir, mayaver, lastver):
    #print('# %s: %s' % (mayaver, sys.executable))

    import maya.standalone
    maya.standalone.initialize(name='python')

    _checkModules(basedir, mayaver, lastver, 'api1.', ['maya.OpenMaya', 'maya.OpenMayaAnim'])
    _checkModules(basedir, mayaver, lastver, 'api2.', ['maya.api.OpenMaya', 'maya.api.OpenMayaAnim'])


def _checkModules(basedir, mayaver, lastver, dirprefix, modnames):
    decideClsFname = lambda ver: _os_path_join(basedir, dirprefix + 'classes', ver + '.txt')
    decideAttrFname = lambda ver: _os_path_join(basedir, dirprefix + 'class_attrs', ver + '.txt')
    decideClsDiffFname = lambda ver: _os_path_join(basedir, dirprefix + 'classes', 'diff', ver + '.txt')
    decideAttrDiffFname = lambda ver: _os_path_join(basedir, dirprefix + 'class_attrs', 'diff', ver + '.txt')

    cls_fname = decideClsFname(mayaver)
    attr_fname = decideAttrFname(mayaver)
    clsnames = None  # _readLinesFromFile(cls_fname)
    attrnames = None  # _readLinesFromFile(attr_fname)

    if clsnames is None or attrnames is None:
        clsnames = []
        attrnames = []
        for modname in modnames:
            clss, attrs = _getModuleContents(modname, cls_fname, attr_fname)
            clsnames.extend(clss)
            attrnames.extend(attrs)
        clsnames.sort()
        attrnames.sort()
        _writeLinesToFile(cls_fname, clsnames)
        _writeLinesToFile(attr_fname, attrnames)

    if lastver:
        last_clsnames = _readLinesFromFile(decideClsFname(lastver))
        cls_add, cls_del = _checkDiff(decideClsDiffFname(mayaver), clsnames, last_clsnames)
        last_attrnames = _readLinesFromFile(decideAttrFname(lastver))
        attr_add, attr_del = _checkDiff(decideAttrDiffFname(mayaver), attrnames, last_attrnames)
        print('# %s: %s: classes=%d(+%d,-%d), class.attrs=%d(+%d,-%d)' % (
            mayaver, dirprefix, len(clsnames), cls_add, cls_del, len(attrnames), attr_add, attr_del))
    else:
        print('# %s: %s: classes=%d, class.attrs=%d' % (
            mayaver, dirprefix, len(clsnames), len(attrnames)))
    return clsnames, attrnames


def _getModuleContents(modname, cls_fname, attr_fname):
    __import__(modname)
    mod = sys.modules[modname]

    modkey = '_' + '_'.join(modname.split('.'))

    base, ext = _os_path_splitext(cls_fname)
    cls_fname = base + modkey + ext
    base, ext = _os_path_splitext(attr_fname)
    attr_fname = base + modkey + ext

    regex_match = re.compile(r'^M[A-Z].+$').match
    tester = lambda x: regex_match(x) and isinstance(getattr(mod, x), type)
    clsnames = sorted([x for x in dir(mod) if tester(x)])

    attrnames = []
    for name in clsnames:
        cls = getattr(mod, name)
        pre = name + '.'
        attrnames.extend(sorted([(pre + x) for x in dir(cls) if not x.startswith('_')]))

    _writeLinesToFile(cls_fname, clsnames)
    _writeLinesToFile(attr_fname, attrnames)

    return clsnames, attrnames


def _checkDiff(fname, news, olds):
    newSet = set(news)
    oldSet = set(olds)
    addSet = newSet.difference(oldSet)
    delSet = oldSet.difference(newSet)
    diff = [(('D ' if x in delSet else 'A ') + x) for x in sorted(addSet.union(delSet))]
    _writeLinesToFile(fname, diff)
    return len(addSet), len(delSet)


def _writeLinesToFile(fname, lines):
    path = _os_path_dirname(fname)
    if not _os_path_exists(path):
        _os_makedirs(path)
    with open(fname, 'w') as file:
        file.write('\n'.join(lines))


def _readLinesFromFile(fname):
    if _os_path_exists(fname):
        with open(fname, 'r') as file:
            return [x.rstrip() for x in file]
    return []


#------------------------------------------------------------------------------
def doit():
    thisdir, thismod = _os_path_split(_os_path_splitext(__file__)[0])
    if not thisdir:
        thisdir = '.'

    lastver = None
    for ver, dir in _findMayaDirs():
        callSubProc(thisdir, thismod, 'checkMaya', dir, './result', ver, lastver)
        lastver = ver

if __name__ == '__main__':
    doit()


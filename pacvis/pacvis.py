import pyalpm
import jinja2

from console import start_message, append_message, print_message

handle = pyalpm.Handle("/","/var/lib/pacman")
localdb = handle.get_localdb()
packages = localdb.pkgcache


def resolve_dependency(dep):
    pkg = localdb.get_pkg(dep)
    if pkg is None:
        pkg = pyalpm.find_satisfier(packages, dep)
    return pkg


class PkgInfo:
    all_pkgs = {}

    def __init__(self, name):
        self._name = name
        self._pkg = localdb.get_pkg(name)
        self._deps = [resolve_dependency(dep).name for dep in self._pkg.depends]
        self._requiredby = self._pkg.compute_requiredby()
        self._level = 0
        self._circledeps = []
        PkgInfo.all_pkgs[name] = self

    def name(self):
        return self._name

    def depends(self):
        return self._deps

    @classmethod
    def get(cls, pkg):
        return cls.all_pkgs[pkg]

    @classmethod
    def find_all(cls):
        for pkg in packages:
            PkgInfo(pkg.name)
        return cls.all_pkgs

    @classmethod
    def find_circles(cls):
        """
            https://zh.wikipedia.org/wiki/Tarjan%E7%AE%97%E6%B3%95
        """
        cls.stack = list()
        cls.indexes = dict()
        cls.lowlinks = dict()
        cls.index = 0

        def strongconnect(pkg):
            cls.indexes[pkg] = cls.index
            cls.lowlinks[pkg] = cls.index
            cls.index += 1
            cls.stack.append(pkg)
            for dep in cls.get(pkg).depends():
                if dep not in cls.indexes:
                    strongconnect(dep)
                    cls.lowlinks[pkg] = min(cls.lowlinks[pkg], cls.lowlinks[dep])
                elif dep in cls.stack:
                    cls.lowlinks[pkg] = min(cls.lowlinks[pkg], cls.indexes[dep])
            if cls.lowlinks[pkg] == cls.indexes[pkg]:
                cirdeps = []
                while True:
                    w = cls.stack.pop()
                    cirdeps.append(w)
                    if (w == pkg):
                        break
                cls.get(pkg)._circledeps = cirdeps

        for pkg in cls.all_pkgs:
            if pkg not in cls.indexes:
                strongconnect(pkg)


    @classmethod
    def topology_sort(cls):
        remain_pkgs = {x for x in cls.all_pkgs}
        start_message("Sorting ")
        while len(remain_pkgs)>0:
            pkg = remain_pkgs.pop()
            origin_level = cls.get(pkg)._level
            append_message("%s %d (remaining %d)" % (pkg, origin_level, len(remain_pkgs)))
            if len(cls.get(pkg).depends()) == 0:
                continue
            max_level = max(cls.get(x)._level for x in cls.get(pkg).depends())
            if max_level + 1 != origin_level:
                cls.get(pkg)._level = max_level + 1
                remain_pkgs.update(set(cls.get(pkg)._requiredby).difference(cls.get(pkg)._circledeps))



def main():
    start_message("Loading local database...")
    PkgInfo.find_all()
    append_message("done")
    start_message("Finding all dependency circles...")
    PkgInfo.find_circles()
    append_message("done")
    PkgInfo.topology_sort()

    print_message("Writing to index.html")
    levels = {}

    nodes = []
    links = []

    for pkg in sorted(PkgInfo.all_pkgs.values(), key=lambda x:x._level):
        if pkg._level in levels:
            pkg._pos = levels[pkg._level]
            levels[pkg._level] += 1
        else:
            levels[pkg._level] = 0
            pkg._pos = 0
        nodes.append({"name": pkg.name(), "level": pkg._level, "pos": pkg._pos})
    for pkg in sorted(PkgInfo.all_pkgs.values(), key=lambda x:x._level):
        for dep in pkg.depends():
            links.append({"from_level": pkg._level, "from_pos": pkg._pos,
             "to_level": PkgInfo.all_pkgs[dep]._level,
             "to_pos": PkgInfo.all_pkgs[dep]._pos})

    env = jinja2.Environment(loader=jinja2.PackageLoader('pacvis', 'templates'))
    template = env.get_template("index.template.html")
    with open("index.html", "w") as content:
        content.write(template.render(nodes=nodes, links=links))


def test():
    start_message("find all packages...")
    PkgInfo.find_all()
    append_message("done")
    start_message("find all dependency circles...")
    PkgInfo.find_circles()
    append_message("done")
    for name,pkg in PkgInfo.all_pkgs.items():
        if len(pkg._circledeps)>1:
            print_message("%s(%s): %s" % (pkg.name(), pkg._circledeps , ", ".join(pkg.depends())))
    PkgInfo.topology_sort()
    for pkg in sorted(PkgInfo.all_pkgs.values(), key=lambda x:x._level):
        print("%s(%d): %s" % (pkg.name(), pkg._level , ", ".join(pkg.depends())))

if __name__ == '__main__':
    main()
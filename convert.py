#!/usr/bin/env python3

import os
from xml.etree.ElementTree import Element, SubElement, Comment, tostring
from xml.etree import ElementTree
from xml.dom import minidom
import logging
import shutil
from pathlib import Path
from sys import stdout, argv
import argparse
from dataclasses import dataclass
from typing import List, Tuple


# adapted from https://www.loggly.com/ultimate-guide/python-logging-basics/
count = 0

logger = logging.getLogger(__name__)
log = logger.info
debug = logger.debug
error = logger.error
logger.setLevel(logging.INFO)


# copied from https://pymotw.com/2/xml/etree/ElementTree/create.html#building-element-nodes
def prettify(elem):
    """Return a pretty-printed XML string for the Element.
    """
    rough_string = ElementTree.tostring(elem, "utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def node(text, children=[]):
    # construct a node
    global count
    a = Element("node")
    idstr = "IDT_%d" % count
    a.set("ID", idstr)
    count += 1
    a.set("TEXT", text)
    a.set("FOLDED", "false")
    for child in children:
        a.append(child)
    return a


# [nodes] -> xmlstring
def makemap(nodes, path):
    # take a list of nodes, and add them to root
    mm = Element("map")
    mm.set("version", "freeplane 1.8.10")
    mm.append(Comment("this is a generated freeplane file"))
    r = node("root", nodes)
    r.set("ROOTDIR", str(path))
    mm.append(r)

    return prettify(mm)


# add body text to a node
def addbody(node, bodytext):
    # add text to the body of the node
    content = Element("richcontent")
    content.set("TYPE", "NOTE")
    # html = SubElement(content, 'html')
    # head = SubElement(html, 'head')
    # body = SubElement(html, 'body')
    # p = SubElement(body, 'p')
    # p.text = bodytext
    content.text = bodytext
    node.append(content)
    return None


def hasbody(node):
    return all(
        child.tag == "richcontent" and child.attrib.get("TYPE", None) == "NOTE"
        for child in node
    )


def getbody(node):
    chilren = list(node)
    assert len(chilren) == 1
    note = chilren[0]
    assert note.attrib["TYPE"] == "NOTE"
    return note.text


# rootnode = node('start')
# final = find_pages(rootnode, 'start')


connections = []

# string path -> node
def filewalk(path, includetext):
    # name = path.relative_to(wikidir)
    name = path.name
    me = node(str(name))
    isdir = os.path.isdir(path)

    me.attrib["ISDIR"] = str(isdir)
    me.attrib["LINK"] = str(path)
    if isdir:
        me.attrib["LOCALIZED_STYLE_REF"] = "styles.topic"

    if os.path.isfile(path):
        # links = wiki.pages.links(name)
        # for link in links:
        # if link["type"] == "local":
        ## print(link)
        # connections.append((link["page"], name))
        if includetext:
            with open(path) as fl:
                addbody(me, fl.read())
        return me
    else:
        for f in os.listdir(path):
            me.append(filewalk(path / f, includetext))
        return me


class enter(object):
    def __init__(self, dir):
        self.dir = dir

        self.predir = os.getcwd()
        if not os.path.isdir(dir):
            log(f"created directory {dir}")
            os.mkdir(dir)

    def __enter__(self):
        os.chdir(self.dir)

    def __exit__(self, *args):
        os.chdir(self.predir)


# write xmlnode to a file
def writetofile(node, inpath, fname):
    with open(fname, "w") as f:
        log("---------DONE---------")
        log(f"---------writing to {fname} ---------")
        f.write(makemap(node, inpath))


def readxml(fname):
    with open(fname, "r") as f:
        return ElementTree.fromstring(f.read())


def xmlnode_to_file(xmlnode, includetext):
    global ex
    debug(f"xmlnode {xmlnode}")

    if "ISDIR" not in xmlnode.attrib:
        global outputdir
        assert Path(os.getcwd()).samefile(outputdir)
        for child in xmlnode:
            xmlnode_to_file(child)
    elif xmlnode.attrib["ISDIR"] == str(True):
        assert not hasbody(xmlnode)
        with enter(Path(xmlnode.attrib["TEXT"]).name):
            for child in xmlnode:
                xmlnode_to_file(child, includetext)
    else:
        assert hasbody(xmlnode)
        with open(Path(xmlnode.attrib["TEXT"]).name, "w") as f:
            f.write(getbody(xmlnode))
    ex = xmlnode


def convert_back_to_directory(inputxmlfile, outputdir, includetext):
    xml = readxml(inputxmlfile)
    rootnode = list(xml)[0]
    with enter(outputdir):
        xmlnode_to_file(rootnode, includetext)


def calculateChanges(inputxmlfile):
    xml = readxml(inputxmlfile)
    rootnode = list(xml)[0]
    rootdir = Path(rootnode.attrib["ROOTDIR"])
    cs = sum([changes(node, rootdir) for node in rootnode], [])
    # cs = changes(rootnode, rootdir)
    return cs


# collect paths of all children of a node
def collectChildren(node):
    # TODO this will fail when we add option to include file text bodies in the mindmap
    if "ISDIR" not in node.attrib:
        # print("node with no attreibs", prettify(node))
        return []
    if node.attrib["ISDIR"] == "True":
        raise InvalidChange(
            f'tried to concatentate directory {node.attrib["LINK"]} to file FILE'
        )

    return [Path(node.attrib["LINK"])] + sum(
        [collectChildren(child) for child in node], []
    )


class InvalidChange(Exception):
    def __init__(self, message):
        self.message = message


def collect_concats(node, path):
    try:
        pathstoappend = collectChildren(node)
        if len(pathstoappend) > 1:
            assert path == pathstoappend[0]
            return [ConcatChange(pathstoappend)]
        else:
            assert len(pathstoappend) != 0
            debug("found no children")
            return []

    except InvalidChange as ic:
        # print(ic)
        raise Exception(ic.message.replace("FILE", str(path)))


# the current node, the calculatedpath, pairs of (from, to) substitutions for paths to apply before returning
def changes(node, calculatedpath, subs=[]):
    childsubs = subs
    ret = []
    if node.tag != "node":
        debug(f"skipping foreign xml node with tag {node.tag}")
        return []

    fname = node.attrib["TEXT"]
    if "ISDIR" not in node.attrib:
        # this is a user created node
        # treat it like a directory
        isdir = True
        path = calculatedpath / fname
        ret.append(MakeDirChange(path))
    else:
        isdir = node.attrib["ISDIR"] == "True"
        path = Path(node.attrib["LINK"])
        debug(fname)

    newpath = calculatedpath / fname
    oldpath = path

    if newpath != oldpath:  # DIFFERENCE FOUND, apply move operation
        # print('diff found')
        if isdir:
            assert newpath.is_absolute()
            assert oldpath.is_absolute()
            ret.append(MoveChange(oldpath, newpath))
            # add a substitution for when we recurse.
            childsubs = subs + [(oldpath, newpath)]
            # ret.extend(sum((changes(child, oldpath, subs = subs + [(oldpath, newpath)]) for child in node), []))
        else:
            ret.append(MoveChange(oldpath, newpath))
            # ret.extend(sum((changes(child, newpath) for child in node), []))

    # recurse. if we are a file, collect children to be appended. if we are a dir, simple recurse
    if isdir:
        ret.extend(sum((changes(child, newpath, subs=childsubs) for child in node), []))
    else:
        ret.extend(collect_concats(node, path))

    for c in ret[:]:
        c.subst(subs)
        if c.is_moot():
            ret.remove(c)
            del c

    return ret


# only added in python 3.9
def is_relative_to(a, b):
    try:
        a.relative_to(b)
        return True
    except:
        return False


class Change:
    def subst_path(path, subs: List[Tuple[Path, Path]]):
        assert path.is_absolute()
        for frm, to in subs:
            if is_relative_to(path, frm):
                return to / path.relative_to(frm)
        return path

    def is_moot(self):
        return False


@dataclass
class MoveChange(Change):
    frm: Path
    to: Path

    def __post_init__(self):
        self.frm = self.frm.absolute()
        self.to = self.to.absolute()

    def subst(self, subs):
        self.frm = Change.subst_path(self.frm, subs)
        self.to = Change.subst_path(self.to, subs)

    def as_command(self):
        return f"mv {self.frm} {self.to}"

    def is_moot(self):
        if self.frm == self.to:
            debug(f"move {self} is moot")
            return True
        return False


@dataclass
class MakeDirChange(Change):
    dir: Path

    def __post_init__(self):
        self.dir = self.dir.absolute()

    def subst(self, subs):
        self.dir = Change.subst_path(self.dir, subs)

    def as_command(self):
        return f"mkdir {self.dir}"


@dataclass
class ConcatChange(Change):
    toconcat: List[Path]

    def __post_init__(self):
        assert len(self.toconcat) >= 2
        self.toconcat = [x.resolve() for x in self.toconcat]

    def subst(self, subs):
        self.toconcat = [Change.subst_path(x, subs) for x in self.toconcat]

    def as_command(self):
        # print(self.toconcat)
        command = ""
        first = self.toconcat[0]
        for file in self.toconcat[1:]:
            command += f"cat {file} >> {first} && rm {file}\n"
        return command.rstrip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="convert directories to mind maps and back"
    )
    parser.add_argument("--f")
    subparser = parser.add_subparsers()

    applyChanges = subparser.add_parser("apply")
    applyChanges.set_defaults(which="apply")
    readDir = subparser.add_parser("makemap")
    readDir.set_defaults(which="readdir")

    readDir.add_argument("map_fname")
    readDir.add_argument("inputdir")

    applyChanges.add_argument("map_fname")
    # applyChanges.add_argument('-r', '--relative', help='cd into directory and apply changes using relative paths')
    args = parser.parse_args()

    if not hasattr(args, "which"):
        raise Exception("you forgot command. try ./convert.py {apply,makemap}")
    if args.which == "readdir":
        wikidir = Path(args.inputdir).resolve()
        mapfname = Path(args.map_fname).resolve()

        log(f"converting {wikidir} to map located at {mapfname}")
        a = filewalk(wikidir, args.f)
        writetofile(a, wikidir, mapfname)

    elif args.which == "apply":
        global outputdir
        # outputdir = Path(args.outputdir).resolve()
        mapfname = Path(args.map_fname).resolve()

        # convert_back_to_directory(mapfname, outputdir, args.f)
        # see changes
        changes = calculateChanges(mapfname)
        # print(f'changes to apply: {len(changes)}')
        for c in changes:
            print(c.as_command())
        print(f"rm {mapfname}")

# mapfname = Path('mindmap/out.mm').resolve()
# see changes
# changes = calculateChanges(mapfname)

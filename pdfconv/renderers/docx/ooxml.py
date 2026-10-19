from __future__ import annotations

import copy

from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Pt

FONT_ATTRS = ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia")


def set_font_name(rpr_owner, name: str) -> None:
    rpr = rpr_owner.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    for a in FONT_ATTRS:
        rf.set(qn(a), name)


def floating_image(paragraph, path: str, x: float, y: float, w: float, h: float,
                   behind: bool, z: int) -> None:

    run = paragraph.add_run()
    run.add_picture(path, width=Pt(w), height=Pt(h))
    inline = run._r.find(".//" + qn("wp:inline"))
    extent = inline.find(qn("wp:extent"))
    docpr = inline.find(qn("wp:docPr"))
    graphic = inline.find(qn("a:graphic"))
    anchor = parse_xml(
        f'<wp:anchor {nsdecls("wp", "a", "pic", "r")} distT="0" distB="0" distL="0" distR="0" '
        f'simplePos="0" relativeHeight="{max(1, z)}" behindDoc="{1 if behind else 0}" locked="1" '
        'layoutInCell="1" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="page"><wp:posOffset>{int(Pt(x))}</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="page"><wp:posOffset>{int(Pt(y))}</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{extent.get("cx")}" cy="{extent.get("cy")}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/></wp:anchor>')
    anchor.append(copy.deepcopy(docpr))
    anchor.append(parse_xml(f'<wp:cNvGraphicFramePr {nsdecls("wp")}/>'))
    anchor.append(copy.deepcopy(graphic))
    inline.getparent().replace(inline, anchor)


WPS_NS = ('xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
          'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
          'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
          'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"')


def floating_textbox(paragraph, content: list, x: float, y: float, w: float, h: float,
                     v_align: str, z: int, shape_id: int) -> None:

    cx, cy = int(Pt(w)), int(Pt(h))
    anchor = {"center": "ctr", "bottom": "b"}.get(v_align, "t")
    drawing = parse_xml(
        f'<w:drawing {WPS_NS}><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" '
        f'relativeHeight="{max(1, z)}" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="page"><wp:posOffset>{int(Pt(x))}</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="page"><wp:posOffset>{int(Pt(y))}</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
        f'<wp:docPr id="{shape_id}" name="TextBox {shape_id}"/><wp:cNvGraphicFramePr/>'
        '<a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
        '<wps:wsp><wps:cNvSpPr txBox="1"/><wps:spPr>'
        f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></wps:spPr>'
        '<wps:txbx><w:txbxContent/></wps:txbx>'
        f'<wps:bodyPr rot="0" vert="horz" wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" '
        f'anchor="{anchor}" anchorCtr="0"><a:noAutofit/></wps:bodyPr>'
        '</wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing>')
    box = drawing.find(".//" + qn("w:txbxContent"))
    for el in content:
        box.append(el)
    if not len(box):
        box.append(OxmlElement("w:p"))
    run = paragraph.add_run()
    run._r.append(drawing)


def set_columns(section, num: int, space_pt: float) -> None:
    sectpr = section._sectPr
    cols = sectpr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sectpr.append(cols)
    for child in list(cols):
        cols.remove(child)
    cols.set(qn("w:num"), str(num))
    cols.set(qn("w:space"), str(int(space_pt * 20)))
    cols.set(qn("w:equalWidth"), "1")


def table_setup(table, widths_pt: list[float], indent_pt: float, cell_margin_pt: float,
                border_sz: int = 4) -> None:
    tblpr = table._tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblpr.append(lay)
    ind = OxmlElement("w:tblInd")
    ind.set(qn("w:w"), str(int(indent_pt * 20)))
    ind.set(qn("w:type"), "dxa")
    tblpr.append(ind)
    m = int(cell_margin_pt * 20)
    tblpr.append(parse_xml(
        f'<w:tblCellMar {nsdecls("w")}><w:top w:w="0" w:type="dxa"/><w:left w:w="{m}" w:type="dxa"/>'
        f'<w:bottom w:w="0" w:type="dxa"/><w:right w:w="{m}" w:type="dxa"/></w:tblCellMar>'))
    tblpr.append(parse_xml(
        f'<w:tblBorders {nsdecls("w")}>' + "".join(
            f'<w:{s} w:val="single" w:sz="{border_sz}" w:space="0" w:color="000000"/>'
            for s in ("top", "left", "bottom", "right", "insideH", "insideV")) + "</w:tblBorders>"))
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths_pt):
        gc.set(qn("w:w"), str(int(w * 20)))
    for row in table.rows:
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        for c, w in zip(row.cells, widths_pt):
            c.width = Pt(w)


def no_widow_control(paragraph) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    wc = OxmlElement("w:widowControl")
    wc.set(qn("w:val"), "0")
    ppr.append(wc)

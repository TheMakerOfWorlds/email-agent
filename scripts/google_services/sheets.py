"""Explicit bounded ranges for reading and writing spreadsheets."""
import re
from google_core import fields, segment, text
from mail_errors import MailError

META = "spreadsheetId,spreadsheetUrl,properties(title,locale,timeZone),sheets(properties)"


def bounded_range(value):
    text(value, 500)
    local = value.rsplit("!", 1)[-1]
    match = re.fullmatch(r"([A-Za-z]{1,3})([1-9][0-9]{0,6})(?::([A-Za-z]{1,3})([1-9][0-9]{0,6}))?", local)
    if not match:
        raise MailError("Use an explicit bounded A1 range, such as 'Sheet1!A1:F50'; whole columns/named ranges are not supported.")
    def col(s):
        n=0
        for c in s.upper():
            n=n*26+ord(c)-64
        return n
    a,b,c,d=match.groups()
    width, height = col(c or a)-col(a)+1, int(d or b)-int(b)+1
    if width < 1 or height < 1 or width*height > 2000:
        raise MailError("Choose an increasing range of at most 2000 cells.")
    return value, width, height


def values_body(data):
    values=data["values"]
    if not isinstance(values,list) or not values or any(not isinstance(r,list) for r in values):
        raise MailError("values must be a nonempty array of row arrays.")
    if sum(len(r) for r in values)>2000 or any(len(r)>100 for r in values):
        raise MailError("Write at most 2000 cells and 100 columns at once.")
    if any(type(v) not in (str,int,float,bool) for r in values for v in r):
        raise MailError("Cells must contain strings, numbers, or booleans.")
    return {"majorDimension":"ROWS", "values":values}


def run(w, action, data, request_id, preview):
    if action in ("open", "get"):
        fields(data, {"id", "tabs_offset"} if action=="open" else {"ref", "tabs_offset"}, ("id",) if action=="open" else ("ref",))
        ident=data["id"] if action=="open" else w.resolve(data["ref"],"sheet")
        out=w.call("sheets","/spreadsheets/"+segment(ident),params={"fields":META})
        offset=data.get("tabs_offset",0)
        if type(offset) is not int or offset<0:
            raise MailError("tabs_offset must be a nonnegative integer.")
        tabs=out.get("sheets",[])
        out["sheets"]=tabs[offset:offset+w.limit]
        out["next_tabs_offset"]=offset+w.limit if offset+w.limit<len(tabs) else None
        return {**out,"ref":w.ref("sheet",ident)}
    if action=="read":
        fields(data,{"ref","range","formulas"},("ref","range"))
        ident=w.resolve(data["ref"],"sheet")
        extent,_,_=bounded_range(data["range"])
        out=w.call("sheets","/spreadsheets/"+segment(ident)+"/values/"+segment(extent),
                   params={"valueRenderOption":"FORMULA" if data.get("formulas") else "FORMATTED_VALUE"})
        return {**out,"ref":data["ref"]}
    if action=="create":
        fields(data,{"title"},("title",))
        text(data["title"],1000)
        def execute():
            out=w.call("sheets","/spreadsheets",method="POST",params={"fields":META},body={"properties":{"title":data["title"]}})
            return {**out,"ref":w.ref("sheet",out["spreadsheetId"])}
        return w.write("sheets.create",data,request_id,execute,preview)
    if action not in ("write","append","clear","format","add-tab"):
        raise MailError("Sheets actions: open, get, read, create, write, append, clear, format, add-tab. Drive search discovers sheets.")
    allowed={"write":{"ref","range","values","interpret"},"append":{"ref","range","values","interpret"},"clear":{"ref","range"},
             "format":{"ref","sheet_id","start_row","end_row","start_column","end_column","cell_format"},"add-tab":{"ref","title"}}[action]
    required={"write":("ref","range","values"),"append":("ref","range","values"),"clear":("ref","range"),
              "format":("ref","sheet_id","start_row","end_row","start_column","end_column","cell_format"),"add-tab":("ref","title")}[action]
    fields(data,allowed,required)
    ident=w.resolve(data["ref"],"sheet")
    path="/spreadsheets/"+segment(ident)
    if action in ("write","append","clear"):
        extent,width,height=bounded_range(data["range"])
        path+="/values/"+segment(extent)
    body=values_body(data) if action in ("write","append") else {}
    if action=="write" and (len(body["values"])>height or any(len(r)>width for r in body["values"])):
        raise MailError("Values would exceed the explicitly selected range.")
    if action=="append" and any(len(r)>width for r in body["values"]):
        raise MailError("Append values would exceed the selected table's column width.")
    if data.get("interpret","RAW") not in ("RAW","USER_ENTERED"):
        raise MailError("interpret must be RAW or explicitly USER_ENTERED to evaluate formulas.")
    if action=="format":
        for key in ("sheet_id","start_row","end_row","start_column","end_column"):
            if type(data[key]) is not int or data[key]<0:
                raise MailError("Formatting bounds are nonnegative integer indexes.")
        if data["end_row"]<=data["start_row"] or data["end_column"]<=data["start_column"] or (data["end_row"]-data["start_row"])*(data["end_column"]-data["start_column"])>2000:
            raise MailError("Select an increasing formatting range of at most 2000 cells.")
        fields(data["cell_format"], {"backgroundColor", "textFormat", "numberFormat", "horizontalAlignment", "verticalAlignment", "wrapStrategy", "borders"})
    def execute():
        if action in ("write","append"):
            out=w.call("sheets",path+(":append" if action=="append" else ""),method="POST" if action=="append" else "PUT",
                params={"valueInputOption":data.get("interpret","RAW"),"includeValuesInResponse":"false",**({"insertDataOption":"INSERT_ROWS"} if action=="append" else {})},body=body)
        elif action=="clear":
            out=w.call("sheets",path+":clear",method="POST",body={})
        else:
            if action=="add-tab":
                text(data["title"],1000)
                edit={"addSheet":{"properties":{"title":data["title"]}}}
            else:
                edit={"repeatCell":{"range":{"sheetId":data["sheet_id"],"startRowIndex":data["start_row"],"endRowIndex":data["end_row"],
                    "startColumnIndex":data["start_column"],"endColumnIndex":data["end_column"]},"cell":{"userEnteredFormat":data["cell_format"]},
                    "fields":",".join("userEnteredFormat."+key for key in data["cell_format"])}}
            out=w.call("sheets",path+":batchUpdate",method="POST",body={"requests":[edit]})
        return {"ref":data["ref"],**out}
    return w.write("sheets."+action,data,request_id,execute,preview)

"""Shared column definitions for the OCLC WMS Circulation Item Inventories report.

Every field position used by the pipeline is derived from EXPECTED_HEADER, so
there are no magic column numbers anywhere else in the package.
"""

EXPECTED_HEADER = [
    "Institution_Symbol",
    "Item_Holding_Location",
    "Item_Permanent_Shelving_Location",
    "Item_Temporary_Shelving_Location",
    "Item_Type",
    "Item_Call_Number",
    "Item_Enumeration_and_Chronology",
    "Author_Name",
    "Title",
    "LHR_Item_Materials_Specified",
    "Material_Format",
    "OCLC_Number",
    "Title_ISBN",
    "Publication_Date",
    "Item_Barcode",
    "LHR_Item_Cost",
    "LHR_Item_Nonpublic_Note",
    "LHR_Item_Public_Note",
    "Item_Status_Current_Status",
    "Item_Due_Date",
    "Item_Issued_Count",
    "Issued_Count_YTD",
    "Item_Soft_Issued_Count",
    "Item_Soft_Issued_Count_YTD",
    "Item_Last_Issued_Date",
    "Item_Last_Inventoried_Date",
    "Item_Deleted_Date",
    "LHR_Date_Entered_on_File",
    "LHR_Item_Acquired_Date",
    "Language_Code",
    "LHR_Item_Call_Number_Normalized",
]

HEADER_LINE = "|".join(EXPECTED_HEADER)
FIELD_COUNT = len(EXPECTED_HEADER)

IDX_ITEM_TYPE = EXPECTED_HEADER.index("Item_Type")
IDX_COST = EXPECTED_HEADER.index("LHR_Item_Cost")
IDX_NONPUBLIC_NOTE = EXPECTED_HEADER.index("LHR_Item_Nonpublic_Note")
IDX_PUBLIC_NOTE = EXPECTED_HEADER.index("LHR_Item_Public_Note")
IDX_STATUS = EXPECTED_HEADER.index("Item_Status_Current_Status")

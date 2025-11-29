from io import TextIOWrapper
import re
from django.shortcuts import render
import os
from django.conf import settings
from django.templatetags.static import static
from django import template
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404 
from django.template import loader
from django.db.models import Prefetch
from decimal import Decimal, InvalidOperation
from .models import *
from .forms import *

from apps.home.models import *
from apps.wgs_app.models import *
from apps.home.forms import *
from apps.wgs_app.forms import *


from django.contrib import messages
# imports for generating pdf
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.templatetags.static import static
from reportlab.lib.units import cm
# for paginator
from django.core.paginator import Paginator
# for dropdown items
from django.contrib import messages
#to auto generate clinic_code, egasp id and clinic
from django.http import JsonResponse, FileResponse
#for importation 
import pandas as pd
from django.utils import timezone
from django.db.models import Q
from django.utils.timezone import now
import csv
from django.utils.dateparse import parse_date
from datetime import datetime
from django.db import IntegrityError
from collections import defaultdict
from django.db import transaction
from django.db.models import Count, Prefetch, Q


# Create your views here.
@login_required(login_url="/login/")
def edit_final_data(request, id):
    # --- Fetch antibiotics lists ---
    # whonet_abx_data = BreakpointsTable.objects.filter(Show=True)
    # whonet_retest_data = BreakpointsTable.objects.filter(Retest=True)


            # get all show=True antibiotics
    whonet_abx_data = BreakpointsTable.objects.filter(Antibiotic_list__Show=True)

    # get all retest antibiotics
    whonet_retest_data = BreakpointsTable.objects.filter(Antibiotic_list__Retest=True)

    # --- Get the isolate record ---
    isolates = get_object_or_404(Final_Data, pk=id)

    # Fetch all entries in one query
    all_entries = Final_AntibioticEntry.objects.filter(ab_idNum_f_referred=isolates)

    # Separate them based on the 'retest' condition
    existing_entries = all_entries.filter(ab_Abx_code__isnull=False)  # Regular entries
    retest_entries = all_entries.filter(ab_Retest_Abx_code__isnull=False)   # Retest entries

    # --- Handle GET request ---
    if request.method == "GET":
        form = Referred_Form(instance=isolates)
        return render(request, "home/Referred_form_final.html", {
            "form": form,
            "whonet_abx_data": whonet_abx_data,
            "whonet_retest_data": whonet_retest_data,
            "edit_mode": True,
            "isolates": isolates,
            "existing_entries": existing_entries,
            "retest_entries": retest_entries,

        })

    # --- Handle POST request ---
    elif request.method == "POST":
        form = Referred_Form(request.POST, instance=isolates)

        if form.is_valid():
            isolates = form.save(commit=False)
            isolates.save()

            
            # --- Handle main antibiotics ---
            for entry in whonet_abx_data:
                abx_code = (entry.Whonet_Abx or "").strip().upper()
                disk_value = request.POST.get(f"disk_{entry.id}") or ""
                disk_enris = (request.POST.get(f"disk_enris_{entry.id}") or "").strip()
                mic_value = request.POST.get(f"mic_{entry.id}") or ""
                mic_enris = (request.POST.get(f"mic_enris_{entry.id}") or "").strip()
                mic_operand = (request.POST.get(f"mic_operand_{entry.id}") or "").strip()
                alert_mic = f"alert_mic_{entry.id}" in request.POST

                try:
                    disk_value = int(disk_value) if disk_value.strip() else None
                except ValueError:
                    disk_value = None

                
                # Debugging: Print the values before saving
                print(f"Saving values for Antibiotic Entry {entry.id}:", {
                    'mic_operand': mic_operand,
                    'disk_value': disk_value,
                    'disk_enris': disk_enris,
                    'mic_value': mic_value,
                    'mic_enris': mic_enris,
                })

                # Get or update antibiotic entry
                antibiotic_entry, created = Final_AntibioticEntry.objects.update_or_create(
                    ab_idNum_f_referred=isolates,
                    ab_Abx_code=abx_code,
                    defaults={
                        "ab_AccessionNo": isolates.f_AccessionNo,
                        "ab_Antibiotic": entry.Antibiotic,
                        "ab_Abx": entry.Abx_code,
                        "ab_Disk_value": disk_value,
                        "ab_Disk_enRIS": disk_enris,
                        "ab_MIC_value": mic_value or None,
                        "ab_MIC_enRIS": mic_enris,
                        "ab_MIC_operand": mic_operand,
                        "ab_R_breakpoint": entry.R_val or None,
                        "ab_I_breakpoint": entry.I_val or None,
                        "ab_SDD_breakpoint": entry.SDD_val or None,
                        "ab_S_breakpoint": entry.S_val or None,
                        "ab_AlertMIC": alert_mic,
                        "ab_Alert_val": entry.Alert_val if alert_mic else '',
                    }
                )

                antibiotic_entry.ab_breakpoints_id.set([entry])

            # Separate loop for Retest Data
            for retest in whonet_retest_data:
                retest_abx_code = retest.Whonet_Abx

                # Fetch user input values for MIC and Disk
                if retest.Disk_Abx:
                    retest_disk_value = request.POST.get(f'retest_disk_{retest.id}')
                    retest_disk_enris = request.POST.get(f"retest_disk_enris_{retest.id}") or ""
                    retest_mic_value = ''
                    retest_mic_enris = ''
                    retest_mic_operand = ''
                    retest_alert_mic = False
                else:
                    retest_mic_value = request.POST.get(f'retest_mic_{retest.id}')
                    retest_mic_enris = request.POST.get(f"retest_mic_enris_{retest.id}") or ""
                    retest_mic_operand = request.POST.get(f'retest_mic_operand_{retest.id}')
                    retest_alert_mic = f'retest_alert_mic_{retest.id}' in request.POST
                    retest_disk_value = ''
                    retest_disk_enris = ''

                # Check and update retest mic_operand if needed
                retest_disk_enris = (retest_disk_enris or '').strip() # Ensure it's a string and strip whitespace
                retest_mic_enris = (retest_mic_enris or '').strip()
                retest_mic_operand = (retest_mic_operand or '').strip()
                
                # Convert `retest_disk_value` safely
                retest_disk_value = int(retest_disk_value) if retest_disk_value and retest_disk_value.strip().isdigit() else None

                # Debugging: Print the values before saving
                print(f"Saving values for Retest Entry {retest.id}:", {
                    'retest_mic_operand': retest_mic_operand,
                    'retest_disk_value': retest_disk_value,
                    'retest_disk_enris': retest_disk_enris,
                    'retest_mic_value': retest_mic_value,
                    'retest_mic_enris': retest_mic_enris,
                    'retest_alert_mic': retest_alert_mic,
                    'retest_alert_val': retest.Alert_val if retest_alert_mic else '',
                })

                # Get or update retest antibiotic entry
                retest_entry, created = Final_AntibioticEntry.objects.update_or_create(
                    ab_idNum_f_referred=isolates,
                    ab_Retest_Abx_code=retest_abx_code,
                    defaults={
                        "ab_Retest_DiskValue": retest_disk_value,
                        "ab_Retest_Disk_enRIS": retest_disk_enris,
                        "ab_Retest_MICValue": retest_mic_value or None,
                        "ab_Retest_MIC_enRIS": retest_mic_enris,
                        "ab_Retest_MIC_operand": retest_mic_operand,
                        "ab_Retest_Antibiotic": retest.Antibiotic,
                        "ab_Retest_Abx": retest.Abx_code,
                        "ab_Ret_R_breakpoint": retest.R_val or None,
                        "ab_Ret_S_breakpoint": retest.S_val or None,
                        "ab_Ret_SDD_breakpoint": retest.SDD_val or None,
                        "ab_Ret_I_breakpoint": retest.I_val or None,
                        "ab_Retest_AlertMIC": retest_alert_mic,
                        "ab_Retest_Alert_val": retest.Alert_val if retest_alert_mic else "",
                    }
                )

                retest_entry.ab_breakpoints_id.set([retest])

            messages.success(request, "Data saved successfully.")
            return redirect("show_data")
        else:
            messages.error(request, "Error: Saving unsuccessful")
            print(form.errors)

    # --- fallback GET render in case POST fails ---
    form = FinalReferred_Form(instance=isolates)
    existing_entries = Final_AntibioticEntry.objects.filter(ab_idNum_f_referred=isolates)
    return render(request, "home/Referred_form_final.html", {
        "form": form,
        "whonet_abx_data": whonet_abx_data,
        "whonet_retest_data": whonet_retest_data,
        "edit_mode": True,
        "isolates": isolates,
        "existing_entries": existing_entries,
        "retest_entries": retest_entries,

    })



# @login_required
# @transaction.atomic
# def upload_final_combined_table(request):
#     """
#     Upload and update Final_Data records only (no antibiotic entries).
#     """
#     form = WGSProjectForm()
#     referred_form = FinalDataUploadForm()

#     if request.method == "POST" and request.FILES.get("FinalDataFile"):
#         try:
#             uploaded_file = request.FILES["FinalDataFile"]
#             file_name = uploaded_file.name.lower()

#             # --- Load file ---
#             if file_name.endswith(".csv"):
#                 wrapper = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig")
#                 df = pd.read_csv(wrapper)
#             elif file_name.endswith((".xlsx", ".xls")):
#                 df = pd.read_excel(uploaded_file)
#             else:
#                 messages.error(request, "Unsupported file format. Please upload CSV or Excel.")
#                 return redirect("upload_final_combined_table")

#             # --- Handle transposed files ---
#             if df.shape[0] < df.shape[1] and "accession_no" not in [c.lower() for c in df.columns]:
#                 df = df.transpose()
#                 df.columns = df.iloc[0].astype(str)
#                 df = df.iloc[1:].reset_index(drop=True)

#             # --- Normalize headers ---
#             original_columns = list(df.columns)
#             df = df.rename(columns=lambda c: str(c).strip())
#             rows = df.to_dict("records")

#             site_codes = set(SiteData.objects.values_list("SiteCode", flat=True))
#             model_fields = {f.name for f in Final_Data._meta.get_fields()}

#             created_ref = updated_ref = 0

#             # --- Field mapping ---
#             FIELD_MAP = {
#                 "accession_no": "f_AccessionNo",
#                 "batch_code": "f_Batch_Code",
#                 "batch_name": "f_Batch_Name",
#                 "site_code": "f_SiteCode",
#                 "batchno": "f_BatchNo",
#                 "total_batch": "f_Total_batch",
#                 "refno": "f_RefNo",
#                 "referral_date": "f_Referral_Date",
#                 "patient_id": "f_Patient_ID",
#                 "first_name": "f_First_Name",
#                 "mid_name": "f_Mid_Name",
#                 "last_name": "f_Last_Name",
#                 "date_birth": "f_Date_Birth",
#                 "age": "f_Age",
#                 "sex": "f_Sex",
#                 "date_admis": "f_Date_Admis",
#                 "nosocomial": "f_Nosocomial",
#                 "diagnosis": "f_Diagnosis",
#                 "diagnosis_icd10": "f_Diagnosis_ICD10",
#                 "ward": "f_Ward",
#                 "ward_type": "f_Ward_Type",
#                 "organismcode": "f_ars_OrgCode",
#                 "service_type": "f_Service_Type",
#                 "spec_num": "f_Spec_Num",
#                 "spec_date": "f_Spec_Date",
#                 "spec_type": "f_Spec_Type",
#                 "reason": "f_Reason",
#                 "growth": "f_Growth",
#                 "urine_colct": "f_Urine_ColCt",
#                 "comments": "f_Comments",
#                 "recommendation": "f_ars_reco",
#             }

#             def normalize_header(h):
#                 if h is None:
#                     return ""
#                 key = re.sub(r"[\s\-_]+", "_", str(h).strip().lower())
#                 return FIELD_MAP.get(key, key)

#             def parse_final_date(val):
#                 if val is None:
#                     return None
#                 if isinstance(val, (pd.Timestamp, datetime)):
#                     try:
#                         return val.date()
#                     except Exception:
#                         return None
#                 s = str(val).strip()
#                 if s in ("", "nan", "NaT", "None", "none"):
#                     return None
#                 try:
#                     dt = pd.to_datetime(s, errors="coerce")
#                     if pd.isna(dt):
#                         return None
#                     return dt.date()
#                 except Exception:
#                     for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y/%m/%d"):
#                         try:
#                             return datetime.strptime(s, fmt).date()
#                         except Exception:
#                             continue
#                 return None

#             def extract_site_code_from_accession(acc):
#                 if not acc:
#                     return ""
#                 s = str(acc)
#                 for code in site_codes:
#                     if re.search(rf"\b{re.escape(code)}\b", s, flags=re.IGNORECASE):
#                         return code
#                 return ""

#             header_map = {normalize_header(orig): orig for orig in original_columns}

#             # --- Process rows ---
#             for raw_row in rows:
#                 if not any([v and str(v).strip() != "" for v in raw_row.values()]):
#                     continue

#                 cleaned_row = {norm_key: raw_row.get(orig_col, "") for norm_key, orig_col in header_map.items()}
#                 accession = str(cleaned_row.get("f_AccessionNo", "")).strip()
#                 batch_code = str(cleaned_row.get("f_Batch_Code", "")).strip()

#                 if not accession:
#                     continue  # skip blank rows

#                 # Parse date fields
#                 date_fields_to_map = {
#                     "f_Referral_Date": cleaned_row.get("f_Referral_Date") or cleaned_row.get("referral_date"),
#                     "f_Spec_Date": cleaned_row.get("f_Spec_Date") or cleaned_row.get("spec_date"),
#                     "f_Date_Birth": cleaned_row.get("f_Date_Birth") or cleaned_row.get("date_birth"),
#                     "f_Date_Admis": cleaned_row.get("f_Date_Admis") or cleaned_row.get("date_admis"),
#                 }
#                 parsed_dates = {k: parse_final_date(v) for k, v in date_fields_to_map.items()}

#                 # Build defaults dictionary
#                 defaults = {}
#                 for norm_key, orig_col in header_map.items():
#                     mapped_field = norm_key if norm_key.startswith("f_") else FIELD_MAP.get(norm_key)
#                     if not mapped_field or mapped_field not in model_fields:
#                         continue
#                     val = cleaned_row.get(norm_key)
#                     if mapped_field in parsed_dates:
#                         defaults[mapped_field] = parsed_dates.get(mapped_field, None)
#                     else:
#                         defaults[mapped_field] = None if (val is None or (isinstance(val, float) and pd.isna(val))) else val

#                 # Safety fallback for mandatory fields
#                 for req_field in ["f_Ward_Type", "f_Nosocomial", "f_Mid_Name"]:
#                     if req_field not in defaults or defaults[req_field] in [None, "", "nan", "NaT"]:
#                         defaults[req_field] = "Unknown"

#                 # Create or update
#                 try:
#                     ref_obj, created = Final_Data.objects.update_or_create(
#                         f_AccessionNo=accession,
#                         f_Batch_Code=batch_code,
#                         defaults=defaults
#                     )
#                 except Exception as e:
#                     print(f"[upload_final_combined_table] Failed saving accession {accession}: {e}")
#                     continue

#                 if created:
#                     created_ref += 1
#                     print(f"[UPLOAD] Created new record for {accession} in batch {batch_code}")
#                 else:
#                     updated_ref += 1
#                     print(f"[UPLOAD] Updated record for {accession} in batch {batch_code}")

#             # --- Summary message ---
#             messages.success(
#                 request,
#                 f"✅ Upload complete! {created_ref} new records and {updated_ref} updated."
#             )
#             return redirect("show_final_data")

#         except Exception as e:
#             import traceback
#             traceback.print_exc()
#             messages.error(request, f" Error during upload: {e}")

#     return render(request, "wgs_app/Add_wgs.html", {
#         "referred_form": referred_form,
#         "form": form,
#     })




# @login_required
# @transaction.atomic
# def upload_final_combined_table(request):
#     """
#     Upload and update Final_Data records using saved field mappings from FieldMapperTool.
#     """
#     form = WGSProjectForm()
#     referred_form = FinalDataUploadForm()

#     if request.method == "POST" and request.FILES.get("FinalDataFile"):
#         try:
#             uploaded_file = request.FILES["FinalDataFile"]
#             file_name = uploaded_file.name.lower()

#             # --- Load file ---
#             if file_name.endswith(".csv"):
#                 wrapper = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig")
#                 df = pd.read_csv(wrapper)
#             elif file_name.endswith((".xlsx", ".xls")):
#                 df = pd.read_excel(uploaded_file)
#             else:
#                 messages.error(request, "Unsupported file format. Please upload CSV or Excel.")
#                 return redirect("upload_final_combined_table")

#             # --- Handle transposed files ---
#             if df.shape[0] < df.shape[1] and "accession_no" not in [c.lower() for c in df.columns]:
#                 df = df.transpose()
#                 df.columns = df.iloc[0].astype(str)
#                 df = df.iloc[1:].reset_index(drop=True)

#             # --- Load user field mappings from FieldMapping model ---
#             user_mappings = dict(
#                 FieldMapping.objects.filter(user=request.user)
#                 .values_list("raw_field", "mapped_field")
#             )

#             # --- Apply user mappings (renames columns) ---
#             if user_mappings:
#                 df.rename(columns=user_mappings, inplace=True)
#                 print(f"[UPLOAD] Applied user mappings for {len(user_mappings)} fields.")
#             else:
#                 messages.warning(request, "No saved mappings found. Using raw headers.")

#             # --- Normalize headers ---
#             df.columns = [str(c).strip() for c in df.columns]
#             original_columns = list(df.columns)
#             rows = df.to_dict("records")

#             # --- Setup context ---
#             site_codes = set(SiteData.objects.values_list("SiteCode", flat=True))
#             model_fields = {f.name for f in Final_Data._meta.get_fields()}
#             created_ref, updated_ref = 0, 0

#             # --- Date parser ---
#             def parse_final_date(val):
#                 if val is None:
#                     return None
#                 if isinstance(val, (pd.Timestamp, datetime)):
#                     try:
#                         return val.date()
#                     except Exception:
#                         return None
#                 s = str(val).strip()
#                 if s in ("", "nan", "NaT", "None", "none"):
#                     return None
#                 try:
#                     dt = pd.to_datetime(s, errors="coerce")
#                     if pd.isna(dt):
#                         return None
#                     return dt.date()
#                 except Exception:
#                     for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y/%m/%d"):
#                         try:
#                             return datetime.strptime(s, fmt).date()
#                         except Exception:
#                             continue
#                 return None

#             def extract_site_code_from_accession(acc):
#                 if not acc:
#                     return ""
#                 s = str(acc)
#                 for code in site_codes:
#                     if re.search(rf"\b{re.escape(code)}\b", s, flags=re.IGNORECASE):
#                         return code
#                 return ""

#             # --- Process each row ---
#             for raw_row in rows:
#                 if not any([v and str(v).strip() != "" for v in raw_row.values()]):
#                     continue

#                 cleaned_row = {k: ("" if pd.isna(v) else v) for k, v in raw_row.items()}
#                 accession = str(cleaned_row.get("f_AccessionNo", "")).strip()
#                 batch_code = str(cleaned_row.get("f_Batch_Code", "")).strip()

#                 if not accession:
#                     continue  # Skip blank rows

#                 # --- Parse date fields ---
#                 date_fields_to_map = {
#                     "f_Referral_Date": cleaned_row.get("f_Referral_Date"),
#                     "f_Spec_Date": cleaned_row.get("f_Spec_Date"),
#                     "f_Date_Birth": cleaned_row.get("f_Date_Birth"),
#                     "f_Date_Admis": cleaned_row.get("f_Date_Admis"),
#                 }
#                 parsed_dates = {k: parse_final_date(v) for k, v in date_fields_to_map.items()}

#                 # --- Build defaults dict ---
#                 defaults = {}
#                 for k, v in cleaned_row.items():
#                     if k not in model_fields:
#                         continue
#                     if k in parsed_dates:
#                         defaults[k] = parsed_dates[k]
#                     else:
#                         defaults[k] = None if (v in [None, "", "nan", "NaT"]) else v

#                 # --- Safety defaults ---
#                 for req_field in ["f_Ward_Type", "f_Nosocomial", "f_Mid_Name"]:
#                     if req_field not in defaults or defaults[req_field] in [None, "", "nan", "NaT"]:
#                         defaults[req_field] = "Unknown"

#                 # --- Add site code if missing ---
#                 if not defaults.get("f_SiteCode"):
#                     defaults["f_SiteCode"] = extract_site_code_from_accession(accession)

#                 # --- Create or update Final_Data record ---
#                 try:
#                     ref_obj, created = Final_Data.objects.update_or_create(
#                         f_AccessionNo=accession,
#                         f_Batch_Code=batch_code,
#                         defaults=defaults
#                     )
#                 except Exception as e:
#                     print(f"[upload_final_combined_table] Failed saving accession {accession}: {e}")
#                     continue

#                 if created:
#                     created_ref += 1
#                     print(f"[UPLOAD] Created record for {accession}")
#                 else:
#                     updated_ref += 1
#                     print(f"[UPLOAD] Updated record for {accession}")

#             # --- Summary message ---
#             messages.success(
#                 request,
#                 f"Upload complete! {created_ref} new records and {updated_ref} updated."
#             )
#             return redirect("show_final_data")

#         except Exception as e:
#             import traceback
#             traceback.print_exc()
#             messages.error(request, f" Error during upload: {e}")

#     return render(request, "wgs_app/Add_wgs.html", {
#         "referred_form": referred_form,
#         "form": form,
#     })


@login_required
@transaction.atomic
def upload_final_combined_table(request):
    """
    Upload and update Final_Data records only (no antibiotic entries).
    Works seamlessly with FieldMapper-generated Excel (model field headers).
    """
    form = WGSProjectForm()
    referred_form = FinalDataUploadForm()

    if request.method == "POST" and request.FILES.get("FinalDataFile"):
        try:
            uploaded_file = request.FILES["FinalDataFile"]
            file_name = uploaded_file.name.lower()

            # --- Load file ---
            if file_name.endswith(".csv"):
                wrapper = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig")
                df = pd.read_csv(wrapper)
            elif file_name.endswith((".xlsx", ".xls")):
                df = pd.read_excel(uploaded_file)
            else:
                messages.error(request, "Unsupported file format. Please upload CSV or Excel.")
                return redirect("upload_final_combined_table")

            # --- Normalize columns while preserving model-style fields (f_ prefixes) ---
            def normalize_header(c):
                c = str(c).strip()
                if c.startswith("f_"):
                    return c  # preserve mapped model fields
                return (
                    c.lower()
                    .replace(" ", "")
                    .replace("__", "_")
                )

            df.columns = [normalize_header(c) for c in df.columns]

            print("\n[DEBUG] Headers after normalization:", list(df.columns))

            # --- Handle transposed sheet case ---
            if df.shape[0] < df.shape[1] and "f_AccessionNo" not in df.columns:
                df = df.transpose()
                df.columns = df.iloc[0].astype(str)
                df = df.iloc[1:].reset_index(drop=True)

            rows = df.to_dict("records")

            site_codes = set(SiteData.objects.values_list("SiteCode", flat=True))
            model_fields = {f.name for f in Final_Data._meta.get_fields()}

            created_ref = updated_ref = 0

            # --- Helper functions ---
            def parse_final_date(val):
                if val is None or str(val).strip().lower() in ["nan", "nat", "none", ""]:
                    return None
                try:
                    dt = pd.to_datetime(val, errors="coerce")
                    return None if pd.isna(dt) else dt.date()
                except Exception:
                    try:
                        return datetime.strptime(str(val), "%Y-%m-%d").date()
                    except Exception:
                        return None

            def extract_site_code_from_accession(acc):
                if not acc:
                    return ""
                s = str(acc)
                for code in site_codes:
                    if re.search(rf"\b{re.escape(code)}\b", s, flags=re.IGNORECASE):
                        return code
                return ""

            # --- Process each record ---
            for raw_row in rows:
                if not any(v and str(v).strip() != "" for v in raw_row.values()):
                    continue

                cleaned_row = {k: v for k, v in raw_row.items() if v not in [None, "nan", "NaT"]}
                accession = str(cleaned_row.get("f_AccessionNo", "") or cleaned_row.get("f_accessionno", "")).strip()
                batch_code = str(cleaned_row.get("f_Batch_Code", "") or cleaned_row.get("f_batch_code", "")).strip()

                if not accession:
                    continue

                # Parse date fields dynamically
                for date_field in ["f_Referral_Date", "f_Spec_Date", "f_Date_Birth", "f_Date_Admis"]:
                    if date_field in cleaned_row:
                        cleaned_row[date_field] = parse_final_date(cleaned_row[date_field])

                # Auto extract site code if missing
                if not cleaned_row.get("f_SiteCode"):
                    cleaned_row["f_SiteCode"] = extract_site_code_from_accession(accession)

                # Keep only valid model fields
                valid_fields = {k: v for k, v in cleaned_row.items() if k in model_fields}

                # Fallback for required text fields
                for req_field in ["f_Ward_Type", "f_Nosocomial", "f_Mid_Name"]:
                    if req_field not in valid_fields or not valid_fields[req_field]:
                        valid_fields[req_field] = "Unknown"

                try:
                    ref_obj, created = Final_Data.objects.update_or_create(
                        f_AccessionNo=accession,
                        f_Batch_Code=batch_code,
                        defaults=valid_fields
                    )
                    if created:
                        created_ref += 1
                        print(f"[UPLOAD] Created: {accession}")
                    else:
                        updated_ref += 1
                        print(f"[UPLOAD] Updated: {accession}")

                except Exception as e:
                    print(f"[ERROR] Failed to save accession {accession}: {e}")
                    continue

            messages.success(
                request,
                f"Upload complete! {created_ref} new records, {updated_ref} updated."
            )
            return redirect("show_final_data")

        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f"Error during upload: {e}")

    # --- Default GET render ---
    return render(request, "wgs_app/Add_wgs.html", {
        "referred_form": referred_form,
        "antibiotic_form": FinalAntibioticUploadForm(),
        "form": form,
    })





@login_required
def show_final_data(request):
    finaldata_summaries = Final_Data.objects.all().order_by("f_Referral_Date")  # optional ordering

    total_records = Final_Data.objects.count()
     # Paginate the queryset to display 20 records per page
    paginator = Paginator(finaldata_summaries, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Render the template with paginated data
    return render(
        request,
        "wgs_app/show_final_data.html",
        {"page_obj": page_obj,
         "total_records": total_records,
         },  # only send page_obj
    )




@login_required
def delete_final_data(request, pk):
    final_item = get_object_or_404(Final_Data, pk=pk)

    if request.method == "POST":
        final_item.delete()
        messages.success(request, f"Record {final_item.f_AccessionNo} deleted successfully!")
        return redirect('show_final_data')  # <-- Correct URL name

    messages.error(request, "Invalid request for deletion.")
    return redirect('show_final_data')  # <-- Correct URL name


@login_required
def delete_all_final_data(request):
    Final_Data.objects.all().delete()
    messages.success(request, "Final Referred Isolates have been deleted successfully.")
    return redirect('show_final_data')  # Redirect to the table view




@login_required
def delete_finaldata_by_date(request):
    if request.method == "POST":
        upload_date_str = request.POST.get("upload_date")
        print(" Received upload_date_str:", upload_date_str)

        if not upload_date_str:
            messages.error(request, "Please select an upload date to delete.")
            return redirect("show_final_data")

        # Use Django’s date parser
        upload_date = parse_date(upload_date_str)

        if not upload_date:
            messages.error(request, f"Invalid date format: {upload_date_str}")
            return redirect("show_final_data")

        deleted_count, _ = Final_Data.objects.filter(Date_uploaded_fd=upload_date).delete()
        messages.success(request, f" Deleted {deleted_count} Final Isolates records uploaded on {upload_date}.")
        return redirect("show_final_data")

    messages.error(request, "Invalid request method.")
    return redirect("show_final_data")





#uploading antibiotic entries
# @login_required
# @transaction.atomic
# def upload_antibiotic_entries(request):
#     if request.method != "POST" or not request.FILES.get("FinalAntibioticFile"):
#         return render(request, "wgs_app/Add_wgs.html", {
#             "form": WGSProjectForm(),
#             "antibiotic_form": FinalAntibioticUploadForm(),
#             "referred_form": FinalAntibioticUploadForm(),
#         })

#     try:
#         uploaded_file = request.FILES["FinalAntibioticFile"]
#         file_name = uploaded_file.name.lower()

#         # --------------------------
#         # LOAD FILE
#         # --------------------------
#         if file_name.endswith(".csv"):
#             wrapper = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig")
#             df = pd.read_csv(wrapper)
#         else:
#             df = pd.read_excel(uploaded_file)

#         df.columns = df.columns.str.strip().str.lower()

#         if "f_accessionno" not in df.columns or "year" not in df.columns:
#             messages.error(request, "Missing required columns: f_accessionno, year")
#             return redirect("upload_antibiotic_entries")

#         # --------------------------
#         # HELPER: clean numeric value
#         # --------------------------
#         def clean_numeric(val):
#             if pd.isna(val):
#                 return None

#             val = str(val).strip()

#             # Ignore text or special characters
#             if val in ["", "-", "ND", "NOT DONE", "NA"]:
#                 return None

#             # Remove operand part for MIC parsing
#             val = val.lstrip("<=>").strip()

#             try:
#                 num = float(val)
#                 if abs(num) <= 99.999:
#                     return round(num, 3)
#             except:
#                 return None

#             return None

#         # --------------------------
#         # HELPER: extract operand (MIC only)
#         # --------------------------
#         def extract_operand(raw):
#             if raw is None or pd.isna(raw):
#                 return ""
#             raw = str(raw).strip()
#             if raw.startswith(("≤", "<=", "<", ">=", ">")):
#                 if raw.startswith("≤"): return "≤"
#                 if raw.startswith("<="): return "<="
#                 if raw.startswith("<"): return "<"
#                 if raw.startswith(">="): return ">="
#                 if raw.startswith(">"): return ">"
#             return ""

#         # -----------------------------------
#         # DETECT ANTIBIOTIC COLUMNS
#         # -----------------------------------
#         abx_codes = [c for c in df.columns if c not in ["f_accessionno", "year"]]

#         # -----------------------------------
#         # PREFETCH ALL Final_Data
#         # -----------------------------------
#         accessions = df["f_accessionno"].astype(str).str.strip().unique()
#         acc_refs = {r.f_AccessionNo: r for r in Final_Data.objects.filter(f_AccessionNo__in=accessions)}

#         created = updated = skipped = errors = 0

#         for idx, row in df.iterrows():
#             accession = str(row["f_accessionno"]).strip()
#             year = str(row["year"]).strip()

#             ref = acc_refs.get(accession)
#             if not ref:
#                 skipped += 1
#                 continue

#             for abx in abx_codes:
#                 raw = row.get(abx)
#                 if pd.isna(raw) or str(raw).strip() in ["", "nan"]:
#                     continue

#                 raw_str = str(raw).strip()

#                 # Determine if MIC or DISK
#                 abx_upper = abx.upper()
#                 is_mic = "_NM" in abx_upper or "MIC" in abx_upper
#                 is_disk = "_ND" in abx_upper or "DISK" in abx_upper or not is_mic

#                 operand = extract_operand(raw_str) if is_mic else ""

#                 numeric_val = clean_numeric(raw_str)
#                 if numeric_val is None:
#                     numeric_val = None

#                 # Extract RIS
#                 ris = ""
#                 if raw_str.upper() in ["R", "S", "I", "SDD"]:
#                     ris = raw_str.upper()

#                 # Correct RIS placement
#                 mic_ris = ris if is_mic else ""
#                 disk_ris = ris if is_disk else ""

#                 entry_data = {
#                     "ab_Abx": abx,
#                     "ab_Abx_code": abx,
#                     "ab_AccessionNo": accession,
#                     "ab_MIC_value": numeric_val if is_mic else None,
#                     "ab_Disk_value": numeric_val if is_disk else None,
#                     "ab_MIC_enRIS": mic_ris,
#                     "ab_Disk_enRIS": disk_ris,
#                     "ab_MIC_operand": operand if is_mic else "",
#                 }

#                 try:
#                     obj, created_flag = Final_AntibioticEntry.objects.update_or_create(
#                         ab_idNum_f_referred=ref,
#                         ab_Abx_code=abx,
#                         defaults=entry_data,
#                     )

#                     if created_flag:
#                         created += 1
#                     else:
#                         updated += 1

#                 except Exception as e:
#                     errors += 1
#                     print(f"[UPLOAD ERROR] Row {idx}, Abx {abx}: {e}")

#         messages.success(request,
#             f"Upload finished: {created} created, {updated} updated, {skipped} skipped, {errors} errors"
#         )
#         return redirect("show_final_data")

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         messages.error(request, f"Fatal upload error: {str(e)}")
#         return redirect("upload_antibiotic_entries")



# @login_required
# @transaction.atomic
# def upload_antibiotic_entries(request):
#     """
#     Final, validated version — full operand support (embedded or separate column)
#     """

#     if request.method != "POST" or not request.FILES.get("FinalAntibioticFile"):
#         messages.error(request, "No file uploaded.")
#         return redirect("upload_antibiotic_entries")

#     try:
#         uploaded_file = request.FILES["FinalAntibioticFile"]
#         file_name = uploaded_file.name.lower()

#         # --------------------------
#         # LOAD FILE
#         # --------------------------
#         if file_name.endswith(".csv"):
#             wrapper = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig")
#             df = pd.read_csv(wrapper)
#         else:
#             df = pd.read_excel(uploaded_file)

#         # Normalize column names
#         df.columns = df.columns.str.strip().str.lower()

#         # Required fields
#         if "f_accessionno" not in df.columns or "year" not in df.columns:
#             messages.error(request, "Missing required columns: f_accessionno, year")
#             return redirect("upload_antibiotic_entries")

#         # --------------------------
#         # NUMERIC CLEANER
#         # --------------------------
#         def clean_numeric(val):
#             if pd.isna(val):
#                 return None

#             val = str(val).strip()

#             # Ignore text or special characters
#             if val in ["", "-", "ND", "NOT DONE", "NA"]:
#                 return None

#             # Remove operand part for MIC parsing
#             val = val.lstrip("<=>").strip()

#             try:
#                 num = float(val)
#                 if abs(num) <= 99.999:
#                     return round(num, 3)
#             except:
#                 return None

#             return None

#         # --------------------------
#         # OPERAND EXTRACTOR
#         # --------------------------
#         def extract_operand(raw):
#             if raw is None:
#                 return ""
#             raw = str(raw).strip()
#             for op in ["≤", "<=", "<", ">=", ">"]:
#                 if raw.startswith(op):
#                     return op
#             return ""

#         # --------------------------
#         # IDENTIFY ANTIBIOTIC COLUMNS
#         # --------------------------
#         base_cols = ["f_accessionno", "year"]
#         abx_columns = [c for c in df.columns if c not in base_cols]

#         accession_values = df["f_accessionno"].astype(str).str.strip().unique()
#         ref_map = {
#             r.f_AccessionNo: r
#             for r in Final_Data.objects.filter(f_AccessionNo__in=accession_values)
#         }

#         created = updated = skipped = errors = 0

#         # --------------------------
#         # MAIN IMPORT LOOP
#         # --------------------------
#         for idx, row in df.iterrows():

#             accession = str(row["f_accessionno"]).strip()
#             ref = ref_map.get(accession)

#             if not ref:
#                 skipped += 1
#                 continue

#             for col in abx_columns:
#                 raw = row.get(col)

#                 # skip blank
#                 if raw is None or (isinstance(raw, float) and pd.isna(raw)) or str(raw).strip() == "":
#                     continue

#                 raw_str = str(raw).strip()
#                 col_upper = col.upper()

#                 # Detect MIC and ND antibiotics
#                 is_mic_col = any(x in col_upper for x in ["_NM", "MIC"])
#                 is_disk_col = (("_ND" in col_upper) or ("DISK" in col_upper)) and not is_mic_col

#                 # Extract operand ALWAYS
#                 operand = extract_operand(raw_str)

#                 # If separate operand column exists, override
#                 separate_op_col = f"{col.lower()}_op"
#                 if separate_op_col in df.columns:
#                     extra_operand = row.get(separate_op_col)
#                     if extra_operand and str(extra_operand).strip().lower() not in ["", "nan"]:
#                         operand = str(extra_operand).strip()

#                 # --------------------------
#                 # SAFE RIS extraction
#                 # --------------------------
#                 ris = ""
#                 ris_col = f"{col.lower()}_ris"

#                 if ris_col in df.columns:
#                     ris_raw = row.get(ris_col, "")
#                     ris = str(ris_raw).strip().upper()

#                 # If raw cell is already RIS
#                 if raw_str.upper() in ["R", "S", "I", "SDD"]:
#                     ris = raw_str.upper()

#                 # --------------------------
#                 # Numeric value
#                 # --------------------------
#                 numeric_val = clean_numeric(raw_str)
#                 if operand and numeric_val is None:
#                     numeric_val = None

#                 # Prepare model fields
#                 entry_data = {
#                     "ab_Abx": col,
#                     "ab_Abx_code": col,
#                     "ab_AccessionNo": accession,
#                     "ab_MIC_value": numeric_val if is_mic_col else None,
#                     "ab_Disk_value": numeric_val if is_disk_col else None,
#                     "ab_MIC_enRIS": ris if is_mic_col else "",
#                     "ab_Disk_enRIS": ris if is_disk_col else "",
#                     "ab_MIC_operand": operand if is_mic_col else "",
#                 }

#                 try:
#                     obj, created_flag = Final_AntibioticEntry.objects.update_or_create(
#                         ab_idNum_f_referred=ref,
#                         ab_Abx_code=col,
#                         defaults=entry_data,
#                     )

#                     if created_flag:
#                         created += 1
#                     else:
#                         updated += 1

#                 except Exception as e:
#                     errors += 1
#                     print(f"[ERROR] Row {idx}, Abx {col}: {e}")

#         messages.success(
#             request,
#             f"Upload Result → Created: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}"
#         )
#         return redirect("show_final_antibiotic")

#     except Exception as e:
#         transaction.set_rollback(True)
#         messages.error(request, f"Fatal Error: {str(e)}")
#         return redirect("show_final_antibiotic")

# @login_required
# @transaction.atomic
# def upload_antibiotic_entries(request):

#     if request.method != "POST" or "FinalAntibioticFile" not in request.FILES:
#         messages.error(request, "No file uploaded.")
#         return redirect("upload_antibiotic_entries")

#     try:
#         uploaded_file = request.FILES["FinalAntibioticFile"]
#         file_name = uploaded_file.name.lower()

#         # Load CSV/Excel
#         if file_name.endswith(".csv"):
#             wrapper = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig")
#             df = pd.read_csv(wrapper)
#         else:
#             df = pd.read_excel(uploaded_file)

#         df.columns = df.columns.str.strip().str.lower()

#         # Required column
#         if "f_accessionno" not in df.columns:
#             messages.error(request, "Missing column f_accessionno")
#             return redirect("upload_antibiotic_entries")

#         # Numeric cleaner
#         def clean_numeric(val):
#             if pd.isna(val):
#                 return None
#             val = str(val).strip()
#             val = val.lstrip("<=>≥≤").strip()
#             try:
#                 return round(float(val), 3)
#             except:
#                 return None

#         # Operand extractor
#         def extract_operand(raw):
#             raw = str(raw).strip()
#             for op in ["≤", "<=", ">=", "<", ">"]:
#                 if raw.startswith(op):
#                     return op
#             return ""

#         # Map accessions
#         acc_values = df["f_accessionno"].astype(str).str.strip().unique()
#         ref_map = {
#             r.f_AccessionNo: r
#             for r in Final_Data.objects.filter(f_AccessionNo__in=acc_values)
#         }

#         created = updated = skipped = errors = 0

#         # -------------------------------------------------------
#         # MAIN LOOP
#         # -------------------------------------------------------
#         for idx, row in df.iterrows():

#             accession = str(row["f_accessionno"]).strip()
#             ref = ref_map.get(accession)

#             if not ref:
#                 skipped += 1
#                 continue

#             for col in df.columns:
#                 if col in ["f_accessionno", "year"]:
#                     continue

#                 raw = row.get(col)
#                 raw_str = "" if raw is None or pd.isna(raw) else str(raw).strip()

#                 col_upper = col.upper()
#                 parts = col_upper.split("_")
#                 base = parts[0]

#                 # -------------------------------------------------------
#                 # COLUMN TYPE DETECTION (RIS → MIC → DISK → OP)
#                 # -------------------------------------------------------

#                 # 1) Skip RIS columns completely
#                 if col_upper.endswith("_RIS"):
#                     continue

#                 # 2) MIC numeric column: e.g., AMK_NM
#                 if col_upper.endswith("_NM") and col_upper.count("_") == 1:
#                     full_code = col_upper          # AMK_NM
#                     is_mic_col = True
#                     is_disk_col = False

#                 # 3) Disk numeric column: e.g., AMK_ND30
#                 elif "_ND" in col_upper and col_upper.count("_") == 1:
#                     full_code = col_upper          # AMK_ND30
#                     is_mic_col = False
#                     is_disk_col = True

#                 # 4) Operand column: e.g., AMK_MIC_OP
#                 elif col_upper.endswith("_MIC_OP"):
#                     full_code = f"{base}_NM"       # operand belongs to MIC antibiotic
#                     is_mic_col = True
#                     is_disk_col = False

#                 # 5) Anything else → skip
#                 else:
#                     continue

#                 # -------------------------------------------------------
#                 # Extract operand
#                 # -------------------------------------------------------
#                 operand = extract_operand(raw_str)

#                 # Possible separate operand columns
#                 possible_operand_cols = [
#                     f"{col.lower()}_op",
#                     f"{base.lower()}_mic_op",
#                     f"{full_code.lower()}_op",
#                 ]

#                 for op_col in possible_operand_cols:
#                     if op_col in df.columns:
#                         op_val = row.get(op_col)
#                         if op_val not in [None, "", " ", float("nan")]:
#                             operand = str(op_val).strip()
#                             break

#                 # Skip blank numeric with no operand
#                 if raw_str == "" and operand == "":
#                     continue

#                 # -------------------------------------------------------
#                 # Extract RIS
#                 # -------------------------------------------------------
#                 ris = ""
#                 ris_col = f"{col.lower()}_ris"

#                 # If RIS column exists and matches this antibiotic numeric column
#                 if ris_col in df.columns:
#                     ris_raw = row.get(ris_col)
#                     if ris_raw not in [None, "", " "]:
#                         ris = str(ris_raw).strip().upper()

#                 # Embedded RIS (cell contains only R/S/I/SDD)
#                 if raw_str.upper() in ["R", "S", "I", "SDD"]:
#                     ris = raw_str.upper()

#                 # -------------------------------------------------------
#                 # Numeric value
#                 # -------------------------------------------------------
#                 numeric_val = clean_numeric(raw_str)

#                 # -------------------------------------------------------
#                 # Build model entry
#                 # -------------------------------------------------------
#                 entry_data = {
#                     "ab_Abx": base,
#                     "ab_Abx_code": full_code,
#                     "ab_AccessionNo": accession,
#                     "ab_MIC_value": numeric_val if is_mic_col else None,
#                     "ab_Disk_value": numeric_val if is_disk_col else None,
#                     "ab_MIC_operand": operand if is_mic_col else "",
#                     "ab_MIC_enRIS": ris if is_mic_col else "",
#                     "ab_Disk_enRIS": ris if is_disk_col else "",
#                 }

#                 # -------------------------------------------------------
#                 # DB SAVE
#                 # -------------------------------------------------------
#                 try:
#                     obj, created_flag = Final_AntibioticEntry.objects.update_or_create(
#                         ab_idNum_f_referred=ref,
#                         ab_Abx_code=full_code,
#                         defaults=entry_data,
#                     )
#                     created += created_flag
#                     updated += (not created_flag)

#                 except Exception as e:
#                     print(f"[ERROR] Row {idx}, col {col}: {e}")
#                     errors += 1

#         messages.success(
#             request,
#             f"Created: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}"
#         )
#         return redirect("show_final_antibiotic")

#     except Exception as e:
#         transaction.set_rollback(True)
#         messages.error(request, f"Fatal Error: {str(e)}")
#         return redirect("show_final_antibiotic")



@login_required
@transaction.atomic
def upload_antibiotic_entries(request):

    if request.method != "POST" or "FinalAntibioticFile" not in request.FILES:
        messages.error(request, "No file uploaded.")
        return redirect("upload_antibiotic_entries")

    try:
        uploaded_file = request.FILES["FinalAntibioticFile"]
        file_name = uploaded_file.name.lower()

        # ------------------------------------------------
        # LOAD FILE
        # ------------------------------------------------
        if file_name.endswith(".csv"):
            wrapper = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig")
            df = pd.read_csv(wrapper)
        else:
            df = pd.read_excel(uploaded_file)

        # ------------------------------------------------
        # CLEAN COLUMN NAMES (FIXES 90% OF SKIPS)
        # ------------------------------------------------
        import re

        def normalize_col(c):
            c = c.strip()
            c = c.replace("µ", "u")
            c = re.sub(r"[^A-Za-z0-9]+", "_", c)  # remove spaces, hyphens, brackets
            c = re.sub(r"_+", "_", c)
            return c.lower().strip("_")

        df.columns = [normalize_col(c) for c in df.columns]

        # ------------------------------------------------
        # REQUIRED COLUMN
        # ------------------------------------------------
        if "f_accessionno" not in df.columns:
            messages.error(request, "Missing column: f_accessionno")
            return redirect("upload_antibiotic_entries")

        # ------------------------------------------------
        # CLEAN NUMERIC VALUES LIKE 0.06, <0.5, >=64
        # ------------------------------------------------
        def clean_numeric(val):
            if pd.isna(val):
                return None
            s = str(val).strip()

            # remove operand prefix
            s = re.sub(r"^(<=|>=|<|>|≤|≥)", "", s).strip()

            try:
                return round(float(s), 3)
            except:
                return None

        # ------------------------------------------------
        # Extract operand from any messy format
        # ------------------------------------------------
        def extract_operand(val):
            if val is None:
                return ""
            s = str(val).strip()
            for op in ["<=", ">=", "<", ">", "≤", "≥"]:
                if s.startswith(op):
                    return op
            return ""

        # ------------------------------------------------
        # MAP ACCESSION NUMBERS TO Final_Data
        # ------------------------------------------------
        acc_list = df["f_accessionno"].astype(str).str.strip()
        acc_unique = acc_list.unique()

        ref_map = {
            r.f_AccessionNo: r
            for r in Final_Data.objects.filter(f_AccessionNo__in=acc_unique)
        }

        created = updated = skipped = errors = 0
        skip_logs = []

        # ==============================================================
        # MAIN IMPORT LOOP
        # ==============================================================
        for idx, row in df.iterrows():

            accession = str(row["f_accessionno"]).strip()
            ref = ref_map.get(accession)

            if not ref:
                skipped += 1
                skip_logs.append(f"Row {idx}: accession not found: {accession}")
                continue

            # ================================================
            # PROCESS ALL OTHER COLUMNS
            # ================================================
            for col in df.columns:

                if col in ["f_accessionno", "year"]:
                    continue

                raw = row.get(col)
                raw_str = "" if pd.isna(raw) else str(raw).strip()

                # Skip empty columns
                if raw_str == "":
                    skipped += 1
                    skip_logs.append(f"Row {idx}, Col {col}: empty -> skipped")
                    continue

                # Extract RIS separately
                ris = ""
                if raw_str.upper() in ["R", "S", "I", "SDD"]:
                    ris = raw_str.upper()

                # -----------------------------------------------
                # DETECT MIC or DISK TYPE
                # -----------------------------------------------
                is_mic = (
                    col.endswith("_nm")
                    or col.endswith("nm")
                    or "mic" in col
                ) and not col.endswith("_nm_op")

                is_disk = bool(re.match(r".*_nd[0-9]*$", col))

                if not (is_mic or is_disk):
                    continue  # skip unknown column format

                # base antibiotic code
                base = col.split("_")[0].upper()

                # Full antibiotic code:
                full_code = col.upper()

                # -----------------------------------------------
                # Operand
                # -----------------------------------------------
                operand = extract_operand(raw_str)

                # Clean invalid operands
                if operand.lower() in ["nan", "none", "null"]:
                    operand = ""


                # If value contains both operand+value like "<=0.5"
                numeric_val = clean_numeric(raw_str)

                # -----------------------------------------------
                # Extra OP column detection
                # -----------------------------------------------
                op_col1 = f"{col}_op"
                op_col2 = f"{base.lower()}_mic_op"

                for op_col in [op_col1, op_col2]:
                    if op_col in df.columns:
                        raw_op = row.get(op_col)
                        if raw_op not in [None, "", " ", float("nan")]:
                            operand = str(raw_op).strip()

                # -----------------------------------------------
                # RIS COLUMN
                # -----------------------------------------------
                ris_col = f"{col}_ris"
                if ris_col in df.columns:
                    raw_ris = row.get(ris_col)
                    if raw_ris not in [None, "", " "]:
                        ris = str(raw_ris).strip().upper()

                # -----------------------------------------------
                # FINAL CHECK: skip if no useful info
                # -----------------------------------------------
                if not numeric_val and operand == "" and ris == "":
                    skipped += 1
                    skip_logs.append(f"Row {idx}, Col {col}: no numeric/operand/ris -> skipped (raw='{raw_str}')")
                    continue

                # -----------------------------------------------
                # Build DB object fields
                # -----------------------------------------------
                entry_data = {
                    "ab_Abx": base,
                    "ab_Abx_code": full_code,
                    "ab_AccessionNo": accession,
                    "ab_MIC_value": numeric_val if is_mic else None,
                    "ab_Disk_value": numeric_val if is_disk else None,
                    "ab_MIC_operand": operand if is_mic else "",
                    "ab_MIC_enRIS": ris if is_mic else "",
                    "ab_Disk_enRIS": ris if is_disk else "",
                }

                # -----------------------------------------------
                # SAVE TO DATABASE
                # -----------------------------------------------
                try:
                    obj, created_flag = Final_AntibioticEntry.objects.update_or_create(
                        ab_idNum_f_referred=ref,
                        ab_Abx_code=full_code,
                        defaults=entry_data,
                    )
                    if created_flag:
                        created += 1
                    else:
                        updated += 1

                except Exception as e:
                    errors += 1
                    print(f"[ERROR] Row {idx}, Col {col}: {e}")

        # ==============================================================
        # FINISHED
        # ==============================================================

        print("Upload summary:",
              f"Created: {created}",
              f"Updated: {updated}",
              f"Skipped: {skipped}",
              f"Errors: {errors}")

        print("Skip logs (first 50):")
        for log in skip_logs[:50]:
            print(" ", log)

        messages.success(
            request,
            f"Created: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}"
        )
        return redirect("show_final_antibiotic")

    except Exception as e:
        transaction.set_rollback(True)
        messages.error(request, f"Fatal Error: {str(e)}")
        return redirect("show_final_antibiotic")




@login_required
def show_final_antibiotic(request):

    entries = Final_AntibioticEntry.objects.select_related(
        "ab_idNum_f_referred"
    ).order_by("ab_idNum_f_referred__f_AccessionNo")

    abx_data = {}
    abx_columns = set()

    for entry in entries:

        # Skip entries with missing code
        if not entry.ab_Abx_code:
            continue

        acc = entry.ab_idNum_f_referred.f_AccessionNo
        full_code = entry.ab_Abx_code.upper()     # Safe now

        # MIC or DISK detection
        is_mic = full_code.endswith("_NM")
        is_disk = "ND" in full_code

        # Build column names
        col_value = full_code
        col_op    = f"{full_code}_OP"
        col_ris   = f"{full_code}_RIS"

        abx_columns.update([col_value, col_op, col_ris])

        if acc not in abx_data:
            abx_data[acc] = {"item_id": entry.id}

        # Save numeric value
        abx_data[acc][col_value] = (
            entry.ab_MIC_value if is_mic else entry.ab_Disk_value
        ) or ""

        # Save operand
        abx_data[acc][col_op] = (
            entry.ab_MIC_operand if is_mic else ""
        ) or ""

        # Save RIS result
        abx_data[acc][col_ris] = (
            entry.ab_MIC_enRIS if is_mic else entry.ab_Disk_enRIS
        ) or ""

    # Sort antibiotic columns
    abx_columns = sorted(abx_columns)

    # Paginate
    paginated_list = list(abx_data.items())
    paginator = Paginator(paginated_list, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "wgs_app/show_final_antibiotic.html",
        {
            "page_obj": page_obj,
            "abx_data": dict(page_obj.object_list),
            "abx_codes": abx_columns,
            "total_records": len(entries),
        }
    )




def delete_final_antibiotic(request, pk):
    target = get_object_or_404(Final_AntibioticEntry, pk=pk)
    acc = target.ab_idNum_f_referred.f_AccessionNo

    if request.method == "POST":
        Final_AntibioticEntry.objects.filter(
            ab_idNum_f_referred__f_AccessionNo=acc
        ).delete()
        messages.success(request, f"All records for accession {acc} deleted successfully!")
        return redirect('show_final_antibiotic')



@login_required
def delete_all_final_antibiotic(request):
    Final_AntibioticEntry.objects.all().delete()
    messages.success(request, "Final Referred Isolates have been deleted successfully.")
    return redirect('show_final_antibiotic')  # Redirect to the table view




@login_required
def delete_finalantibiotic_by_date(request):
    if request.method == "POST":
        upload_date_str = request.POST.get("upload_date")
        print(" Received upload_date_str:", upload_date_str)

        if not upload_date_str:
            messages.error(request, "Please select an upload date to delete.")
            return redirect("show_final_antitbiotic")

        # Use Django’s date parser
        upload_date = parse_date(upload_date_str)

        if not upload_date:
            messages.error(request, f"Invalid date format: {upload_date_str}")
            return redirect("show_final_antibiotic")

        deleted_count, _ = Final_AntibioticEntry.objects.filter(ab_Date_uploaded_fd=upload_date).delete()
        messages.success(request, f" Deleted {deleted_count} Final Antibiotic entries uploaded on {upload_date}.")
        return redirect("show_final_antibiotic")

    messages.error(request, "Invalid request method.")
    return redirect("show_final_antibiotic")
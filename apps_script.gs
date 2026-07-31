/**
 * JODAH AL-MUSTAQBAL - GOOGLE APPS SCRIPT BACKEND
 * -----------------------------------------------
 * Tab Names: Listings, Leads
 * API Key: luxury_jodah_2024 (change as needed)
 */

const SPREADSHEET_ID = '13HXDBf5sy1twYGxE5vS33-1joa3z4Zld5VtMPrzHEgI';
const API_KEY = 'luxury_jodah_2024_rotated_v2';

function appendWithHeader(sheet, cols, data) {
  const lastCol = Math.max(sheet.getLastColumn(), cols.length);
  const firstRow = sheet.getLastRow() > 0 ? sheet.getRange(1, 1, 1, lastCol).getValues()[0] : [];
  
  // Create header if missing or incorrect
  if (!firstRow[0] || String(firstRow[0]).toLowerCase() !== "timestamp") {
    sheet.getRange(1, 1, 1, cols.length).setValues([cols]);
  }

  const row = cols.map(k => {
    if (k === "timestamp") return new Date();
    let val = data[k] ?? "";
    // Force string for phone fields to prevent scientific notation
    if (k.toLowerCase().includes("phone") && val) return "'" + val;
    return val;
  });

  sheet.appendRow(row);
}

function doGet(e) {
  const action = e.parameter.action;
  const key = e.parameter.key;

  if (key !== API_KEY) {
    return jsonOut({ error: 'Unauthorized' }, 403);
  }

  if (action === 'listings') {
    return getListings();
  }

  return jsonOut({ error: 'Invalid action' }, 400);
}

function doPost(e) {
  try {
    const raw = e && e.postData && e.postData.contents ? e.postData.contents : "";
    const data = raw ? JSON.parse(raw) : {};
    const type = String(data.type || "").trim();

    Logger.log("TYPE_RECEIVED=" + type);

    // 🔒 حماية بسيطة: مفتاح
    const expectedKey = API_KEY; 
    const providedKey = String(data.key || data.API_KEY || "");
    if (expectedKey && providedKey !== expectedKey) {
      return jsonOut({ status: "error", error: "invalid_key" }, 403);
    }

    const ss = SpreadsheetApp.getActiveSpreadsheet();
    Logger.log("SS_NAME=" + ss.getName());

    const OFFER_TAB = "عرض عقار";
    const INQUIRY_TAB = "General_Inquiries";

    // ✅ مسار عرض عقار (إجباري وحصري للشيت الجديد)
    if (type === "عرض عقار") {
      // ID الشيت الجديد
      const NEW_SS_ID = "13HXDBf5sy1twYGxE5vS33-1joa3z4Zld5VtMPrzHEgI"; 
      let newSS;
      try {
        newSS = SpreadsheetApp.openById(NEW_SS_ID);
      } catch (e) {
        return jsonOut({ status: "error", error: "could_not_open_new_sheet", details: String(e) }, 500);
      }

      // محاولة البحث بالاسم أولاً
      let offerSheet = newSS.getSheetByName("عرض عقار");
      
      // Fallback: البحث عن طريق GID إذا تغير الاسم
      if (!offerSheet) {
         const sheets = newSS.getSheets();
         offerSheet = sheets.find(s => s.getSheetId() === 627691346);
      }

      if (!offerSheet) {
        return jsonOut({ status: "error", error: "offer_tab_not_found_in_new_sheet" }, 404);
      }

      const cols = ["timestamp", "owner_name", "phone", "city", "neighborhood", "property_type", "property_age", "listing_type", "category", "area", "price", "floors", "apartments", "rooms", "bathrooms", "images_link", "google_map", "owner_notes"];
      appendWithHeader(offerSheet, cols, data);
      return jsonOut({ status: "success", wrote_to: "New Sheet: عرض عقار" }, 200);
    }

    // ✅ مسار الاستفسارات العامة (Contact Form)
    if (type === "general") {
      const inquirySheet = ss.getSheetByName(INQUIRY_TAB);
      if (!inquirySheet) {
        return jsonOut({ status: "error", error: "inquiry_tab_not_found", tab: INQUIRY_TAB }, 404);
      }

      const cols = ["timestamp", "customerName", "customerPhone", "customerNotes", "propertyId", "listing_id", "propertyType", "city", "district", "price", "area", "status", "ownerName", "ownerPhone", "mapUrl", "services", "counter"];
      appendWithHeader(inquirySheet, cols, data);
      return jsonOut({ status: "success", wrote_to: INQUIRY_TAB }, 200);
    }

    // ✅ مسار الـ Lead (من صفحة العقار - التفاصيل)
    if (type === "lead" || data.listing_id) {
       return handleLead(data);
    }

    // 🛑 رفض أي نوع آخر
    return jsonOut({ status: "error", error: "unsupported_type", got: type }, 400);

  } catch (err) {
    Logger.log("ERROR=" + err);
    return jsonOut({ status: "error", error: String(err) }, 500);
  }
}

function jsonOut(obj, code) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// Handle OPTIONS for CORS preflight
function doOptions(e) {
  const output = ContentService.createTextOutput("");
  output.setMimeType(ContentService.MimeType.TEXT);
  return output;
}

function getListings() {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName('Listings');
  if (!sheet) return jsonOut({ error: 'Tab "Listings" not found' }, 500);

  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) return jsonOut([]);
  
  const headers = data[0].map(h => h.toString().trim().toLowerCase());
  const rows = data.slice(1);

  const listings = rows.map(row => {
    let obj = {};
    headers.forEach((h, i) => {
      obj[h] = row[i];
    });
    return obj;
  }).filter(l => l.id).reverse(); // Latest first

  return jsonOut(listings);
}

function handleLead(data) {
  const { listing_id, name, phone, notes } = data;

  if (!listing_id || !phone) {
    return jsonOut({ error: 'Missing required fields' }, 400);
  }

  const normalizedPhone = normalizePhone(phone);
  if (!normalizedPhone) {
    return jsonOut({ error: 'Invalid Saudi phone number' }, 400);
  }

  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const listingsSheet = ss.getSheetByName('Listings');
  const leadsSheet = ss.getSheetByName('Leads');

  if (!listingsSheet || !leadsSheet) {
    return jsonOut({ error: 'Sheets not found' }, 500);
  }

  // Lookup listing details
  const listingsData = listingsSheet.getDataRange().getValues();
  const headers = listingsData[0].map(h => h.toString().trim().toLowerCase());
  const listingRow = listingsData.find(r => r[headers.indexOf('id')] == listing_id);

  let title = 'N/A', district = 'N/A', price = 'N/A';
  if (listingRow) {
    title = listingRow[headers.indexOf('title')];
    district = listingRow[headers.indexOf('district')];
    price = listingRow[headers.indexOf('price')];
  }

  // Append lead
  leadsSheet.appendRow([
    new Date(),
    listing_id,
    title,
    district,
    price,
    name || 'Anonymous',
    "'" + normalizedPhone, // Force string in sheet
    notes || '',
    'website'
  ]);

  return jsonOut({ ok: true });
}

function normalizePhone(phone) {
  let cleaned = phone.toString().replace(/\D/g, '');
  if (cleaned.startsWith('05') && cleaned.length === 10) {
    return '966' + cleaned.substring(1);
  } else if (cleaned.startsWith('5') && cleaned.length === 9) {
    return '966' + cleaned;
  } else if (cleaned.startsWith('9665') && cleaned.length === 12) {
    return cleaned;
  }
  return null;
}

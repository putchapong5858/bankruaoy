/**
 * ระบบสมาชิกผู้ปกครอง — เรียนพิเศษบ้านครูอ้อย (bankruaoy.com)
 * Backend: Google Apps Script Web App
 * ฐานข้อมูล: Google Sheets
 * ยืนยันตัวตน: LINE Login (LIFF) ID token
 *
 * ─────────────────────────────────────────────
 *  ⚙️  ตั้งค่า 2 บรรทัดข้างล่างนี้ก่อนใช้งาน
 * ─────────────────────────────────────────────
 */

// ID ของ Google Sheets ฐานข้อมูล (ดูได้จาก URL ของชีต ระหว่าง /d/ กับ /edit)
const SHEET_ID = '110pn5xbovgVPA18XzitEzy5ZnRjebbRSY3WU-qQGNiE';

// Channel ID ของ LINE Login channel (ตัวเลขล้วน จากแท็บ Basic settings)
// ⚠️ นี่คือ Channel ID ไม่ใช่ Channel secret — ห้ามใส่ secret ลงในไฟล์นี้
const LINE_CHANNEL_ID = 'ใส่_CHANNEL_ID_ตรงนี้';

// ชื่อแท็บในชีต (ห้ามแก้ถ้าไม่ได้เปลี่ยนชื่อแท็บจริง)
const TAB = {
  students:   'นักเรียน',
  attendance: 'เช็คชื่อ',
  scores:     'คะแนน',
  homework:   'การบ้าน',
  schedule:   'ตารางเรียน',
  news:       'ประกาศ',
  pending:    'รออนุมัติ'
};

/* ══════════════════════════════════════════════
   จุดรับ request
   ══════════════════════════════════════════════ */

function doGet() {
  return json({ ok: true, service: 'baan-kru-aoy-portal', time: new Date().toISOString() });
}

function doPost(e) {
  try {
    const body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    const action = body.action || 'me';

    if (action === 'ping') return json({ ok: true, pong: true });

    const profile = verifyIdToken(body.idToken);   // โยน error ถ้า token ปลอม/หมดอายุ

    if (action === 'me') return json(buildPortal(profile));

    return json({ ok: false, error: 'unknown_action' });
  } catch (err) {
    return json({ ok: false, error: String(err && err.message ? err.message : err) });
  }
}

/* ══════════════════════════════════════════════
   ยืนยัน ID token กับเซิร์ฟเวอร์ LINE
   ══════════════════════════════════════════════ */

function verifyIdToken(idToken) {
  if (!idToken) throw new Error('missing_id_token');
  if (!LINE_CHANNEL_ID || LINE_CHANNEL_ID.indexOf('ใส่_') === 0) {
    throw new Error('ยังไม่ได้ตั้งค่า LINE_CHANNEL_ID ในไฟล์ Code.gs');
  }

  const res = UrlFetchApp.fetch('https://api.line.me/oauth2/v2.1/verify', {
    method: 'post',
    contentType: 'application/x-www-form-urlencoded',
    payload: { id_token: idToken, client_id: String(LINE_CHANNEL_ID) },
    muteHttpExceptions: true
  });

  const data = JSON.parse(res.getContentText() || '{}');
  if (res.getResponseCode() !== 200 || !data.sub) {
    throw new Error('ยืนยันตัวตนกับ LINE ไม่สำเร็จ: ' + (data.error_description || data.error || res.getResponseCode()));
  }
  if (String(data.aud) !== String(LINE_CHANNEL_ID)) throw new Error('channel_mismatch');
  if (data.exp && Number(data.exp) * 1000 < Date.now()) throw new Error('token_expired');

  return { userId: data.sub, displayName: data.name || '', picture: data.picture || '' };
}

/* ══════════════════════════════════════════════
   ประกอบข้อมูลสำหรับหน้าโปรไฟล์
   ══════════════════════════════════════════════ */

function buildPortal(profile) {
  const students = readTab(TAB.students);
  const mine = students.filter(function (r) {
    return String(r['LINE User ID ผู้ปกครอง'] || '').trim() === profile.userId;
  });

  if (!mine.length) {
    recordPending(profile);
    return {
      ok: true,
      status: 'pending',
      lineName: profile.displayName,
      linePicture: profile.picture,
      message: 'บัญชี LINE ของคุณยังไม่ถูกผูกกับนักเรียน กรุณาแจ้งครูอ้อยเพื่อเปิดสิทธิ์'
    };
  }

  const schedule = readTab(TAB.schedule);
  const news = readTab(TAB.news).filter(function (n) {
    const until = n['แสดงถึงวันที่'];
    return !until || String(until) >= today();
  });

  const attendance = readTab(TAB.attendance);
  const scores = readTab(TAB.scores);
  const homework = readTab(TAB.homework);

  const children = mine.map(function (s) {
    const id = String(s['รหัสนักเรียน'] || '').trim();
    const level = String(s['ระดับชั้น'] || '').trim();

    const att = attendance
      .filter(function (a) { return String(a['รหัสนักเรียน'] || '').trim() === id; })
      .sort(descBy('วันที่'));

    const sc = scores
      .filter(function (x) { return String(x['รหัสนักเรียน'] || '').trim() === id; })
      .sort(descBy('วันที่'));

    const hw = homework
      .filter(function (h) {
        const target = String(h['รหัสนักเรียน'] || '').trim();
        if (target === id) return true;
        if (target === '' || target === 'ทั้งห้อง' || target === 'ทั้งชั้น') {
          const lv = String(h['ระดับชั้น'] || '').trim();
          return lv === '' || lv === level;
        }
        return false;
      })
      .sort(descBy('กำหนดส่ง'));

    return {
      id: id,
      name: s['ชื่อ-นามสกุล'] || '',
      nickname: s['ชื่อเล่น'] || '',
      level: level,
      hoursBought: num(s['ชั่วโมงที่ซื้อ']),
      hoursUsed: num(s['ชั่วโมงที่ใช้ไป']),
      hoursLeft: s['ชั่วโมงคงเหลือ'] === '' || s['ชั่วโมงคงเหลือ'] == null
        ? num(s['ชั่วโมงที่ซื้อ']) - num(s['ชั่วโมงที่ใช้ไป'])
        : num(s['ชั่วโมงคงเหลือ']),
      paymentStatus: s['สถานะการจ่ายเงิน'] || '',
      expiry: s['วันหมดอายุคอร์ส'] || '',
      note: s['หมายเหตุ'] || '',
      attendance: att.slice(0, 30),
      scores: sc.slice(0, 30),
      homework: hw.slice(0, 30)
    };
  });

  return {
    ok: true,
    status: 'ok',
    lineName: profile.displayName,
    linePicture: profile.picture,
    parentName: mine[0]['ชื่อผู้ปกครอง'] || profile.displayName,
    children: children,
    schedule: schedule,
    news: news
  };
}

/* ══════════════════════════════════════════════
   บันทึกผู้ปกครองที่รอครูอ้อยอนุมัติ
   ══════════════════════════════════════════════ */

function recordPending(profile) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(5000);
    const sh = book().getSheetByName(TAB.pending);
    if (!sh) return;

    const values = sh.getDataRange().getValues();
    for (var i = 1; i < values.length; i++) {
      if (String(values[i][0]).trim() === profile.userId) return;   // มีอยู่แล้ว ไม่เพิ่มซ้ำ
    }
    sh.appendRow([
      profile.userId,
      profile.displayName,
      Utilities.formatDate(new Date(), 'Asia/Bangkok', 'yyyy-MM-dd HH:mm'),
      '',
      'รออนุมัติ'
    ]);
  } catch (err) {
    // ไม่ให้ล้มทั้งคำขอเพียงเพราะบันทึกคิวไม่สำเร็จ
  } finally {
    try { lock.releaseLock(); } catch (e) {}
  }
}

/* ══════════════════════════════════════════════
   ตัวช่วย
   ══════════════════════════════════════════════ */

function book() {
  return SpreadsheetApp.openById(SHEET_ID);
}

/** อ่านแท็บหนึ่งออกมาเป็น array ของ object โดยใช้แถวที่ 1 เป็นชื่อคีย์ */
function readTab(name) {
  const sh = book().getSheetByName(name);
  if (!sh) return [];
  const values = sh.getDataRange().getDisplayValues();
  if (values.length < 2) return [];

  const headers = values[0].map(function (h) { return String(h).trim(); });
  const out = [];

  for (var r = 1; r < values.length; r++) {
    const row = values[r];
    if (row.join('').trim() === '') continue;          // ข้ามแถวว่าง
    const obj = {};
    var hasValue = false;
    for (var c = 0; c < headers.length; c++) {
      if (!headers[c]) continue;
      const v = row[c] == null ? '' : String(row[c]).trim();
      obj[headers[c]] = v;
      if (v !== '') hasValue = true;
    }
    if (hasValue) out.push(obj);
  }
  return out;
}

function descBy(key) {
  return function (a, b) {
    return String(b[key] || '').localeCompare(String(a[key] || ''));
  };
}

function num(v) {
  const n = Number(String(v == null ? '' : v).replace(/,/g, ''));
  return isNaN(n) ? 0 : n;
}

function today() {
  return Utilities.formatDate(new Date(), 'Asia/Bangkok', 'yyyy-MM-dd');
}

function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/* ══════════════════════════════════════════════
   ทดสอบจากในตัวแก้ไข (กด Run ที่ฟังก์ชันนี้)
   ══════════════════════════════════════════════ */

function ทดสอบอ่านชีต() {
  const s = readTab(TAB.students);
  Logger.log('อ่านแท็บนักเรียนได้ ' + s.length + ' แถว');
  Logger.log(JSON.stringify(s[0] || {}, null, 2));
  Logger.log('ตารางเรียน ' + readTab(TAB.schedule).length + ' แถว');
  Logger.log('ประกาศ ' + readTab(TAB.news).length + ' แถว');
}

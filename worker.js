const DEFAULT_ADMIN_TOKEN =
  '52e47f8b4dc49067e340b09e550a350345b035d778bd241662e846ce534087de994285f916624af2396bfccf91c4796d7d505c3941a7813bc33f09804d8abb68'

const COOLDOWN_DAYS = 4
const COOLDOWN_MS = COOLDOWN_DAYS * 24 * 60 * 60 * 1000

const KEY_CHARS = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'

function generateChunk(length = 4) {
  let res = ''
  const randomBytes = new Uint8Array(length)
  crypto.getRandomValues(randomBytes)
  for (let i = 0; i < length; i++) {
    res += KEY_CHARS[randomBytes[i] % KEY_CHARS.length]
  }
  return res
}

function generateKeyCode() {
  return `PX-${generateChunk(4)}-${generateChunk(4)}-${generateChunk(4)}`
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  })
}

function errorResponse(error, status = 400, extra = {}) {
  return jsonResponse({ valid: false, error, ...extra }, status)
}

function verifyAdmin(request, env) {
  const auth = request.headers.get('Authorization') || ''
  const expectedToken = env.ADMIN_SECRET_TOKEN || DEFAULT_ADMIN_TOKEN
  if (!auth.startsWith('Bearer ')) return false
  const token = auth.slice(7).trim()
  return token === expectedToken
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)
    const { pathname } = url

    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
      })
    }

    if (!env.DB) {
      return errorResponse('D1 Database binding (DB) is missing in worker configuration', 500)
    }

    try {
      if (pathname === '/admin/init-db' && request.method === 'POST') {
        if (!verifyAdmin(request, env)) return errorResponse('Unauthorized', 401)

        await env.DB.prepare(`
          CREATE TABLE IF NOT EXISTS supporter_keys (
            key_code TEXT PRIMARY KEY,
            tier TEXT DEFAULT "supporter",
            is_used INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            revoke_reason TEXT,
            bound_to_uuid TEXT,
            bound_hwid TEXT,
            discord_id TEXT,
            last_reset_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            redeemed_at DATETIME
          );
        `).run()

        return jsonResponse({ success: true, message: 'Table supporter_keys initialized successfully' })
      }

      if (pathname === '/admin/generate' && request.method === 'POST') {
        if (!verifyAdmin(request, env)) return errorResponse('Unauthorized', 401)

        const body = await request.json().catch(() => ({}))
        const tier = (body.tier || 'supporter').toLowerCase()
        const discordId = body.discord_id || null
        const count = Math.min(Math.max(parseInt(body.count || 1, 10), 1), 50)
        const customKey = body.custom_key ? String(body.custom_key).trim().toUpperCase() : null

        const createdKeys = []

        for (let i = 0; i < count; i++) {
          const keyCode = customKey && i === 0 ? customKey : generateKeyCode()
          await env.DB.prepare(`
            INSERT INTO supporter_keys (key_code, tier, discord_id)
            VALUES (?, ?, ?)
          `).bind(keyCode, tier, discordId).run()

          createdKeys.push(keyCode)
        }

        return jsonResponse({
          success: true,
          count: createdKeys.length,
          keys: createdKeys,
          tier,
          discord_id: discordId,
        })
      }

      if (pathname === '/admin/lookup' && request.method === 'POST') {
        if (!verifyAdmin(request, env)) return errorResponse('Unauthorized', 401)

        const body = await request.json().catch(() => ({}))
        const { key_code, discord_id } = body

        if (!key_code && !discord_id) {
          return errorResponse('Missing key_code or discord_id parameter', 400)
        }

        const lookupCode = key_code ? String(key_code).trim().toUpperCase() : null
        const lookupDiscord = discord_id ? String(discord_id).trim() : null

        const row = lookupCode
          ? await env.DB.prepare('SELECT * FROM supporter_keys WHERE key_code = ?').bind(lookupCode).first()
          : await env.DB.prepare(
            'SELECT * FROM supporter_keys WHERE discord_id = ? ORDER BY is_used DESC, redeemed_at DESC, created_at DESC LIMIT 1'
          ).bind(lookupDiscord).first()

        if (!row) return jsonResponse({ success: true, found: false })

        return jsonResponse({
          success: true,
          found: true,
          key: {
            key_code: row.key_code,
            tier: row.tier || 'supporter',
            is_used: !!row.is_used,
            is_blocked: !!row.is_blocked,
            revoke_reason: row.revoke_reason || null,
            discord_id: row.discord_id || null,
            bound: !!row.bound_hwid,
            last_reset_at: row.last_reset_at || null,
            redeemed_at: row.redeemed_at || null,
          },
        })
      }

      if (pathname === '/admin/reset-hwid' && request.method === 'POST') {
        if (!verifyAdmin(request, env)) return errorResponse('Unauthorized', 401)

        const body = await request.json().catch(() => ({}))
        const { key_code, discord_id } = body

        if (!key_code && !discord_id) {
          return errorResponse('Missing key_code or discord_id parameter', 400)
        }

        const normalizedKeyCode = key_code ? String(key_code).trim().toUpperCase() : null
        const normalizedDiscordId = discord_id ? String(discord_id).trim() : null

        const keyRecord = normalizedKeyCode
          ? await env.DB.prepare('SELECT * FROM supporter_keys WHERE key_code = ?').bind(normalizedKeyCode).first()
          : await env.DB.prepare(
            'SELECT * FROM supporter_keys WHERE discord_id = ? ORDER BY is_used DESC, redeemed_at DESC, created_at DESC LIMIT 1'
          ).bind(normalizedDiscordId).first()

        if (!keyRecord) {
          return errorResponse(
            normalizedKeyCode
              ? 'Không tìm thấy Supporter Key tương ứng'
              : 'Tài khoản Discord của bạn chưa có Supporter Key nào. Hãy nhận key tri ân trước khi dùng tính năng này.',
            404,
            { no_key: true }
          )
        }

        if (normalizedDiscordId && String(keyRecord.discord_id || '') !== normalizedDiscordId) {
          return errorResponse('Supporter Key này không thuộc về tài khoản Discord của bạn', 403, {
            not_owner: true,
          })
        }

        if (keyRecord.is_blocked) {
          return errorResponse('Key này đã bị thu hồi/khóa, không thể reset HWID', 403, {
            revoked: true,
            reason: keyRecord.revoke_reason,
          })
        }

        if (!keyRecord.is_used) {
          return errorResponse(
            'Supporter Key này chưa được kích hoạt trên thiết bị nào nên không cần giải phóng',
            409,
            { not_activated: true }
          )
        }

        if (keyRecord.last_reset_at) {
          const lastResetTime = new Date(keyRecord.last_reset_at).getTime()
          const now = Date.now()
          const elapsed = now - lastResetTime
          if (elapsed < COOLDOWN_MS) {
            const remainingHours = Math.ceil((COOLDOWN_MS - elapsed) / (1000 * 60 * 60))
            return errorResponse(
              `Bạn vừa reset HWID gần đây. Vui lòng chờ thêm ${remainingHours} giờ nữa (Cooldown: ${COOLDOWN_DAYS} ngày/lần).`,
              429,
              { remaining_hours: remainingHours }
            )
          }
        }

        await env.DB.prepare(`
          UPDATE supporter_keys
          SET bound_hwid = NULL, last_reset_at = CURRENT_TIMESTAMP
          WHERE key_code = ?
        `).bind(keyRecord.key_code).run()

        return jsonResponse({
          success: true,
          message: 'Reset HWID thành công! Người dùng có thể kích hoạt trên thiết bị mới.',
          key_code: keyRecord.key_code,
          discord_id: keyRecord.discord_id,
        })
      }

      if (pathname === '/admin/revoke' && request.method === 'POST') {
        if (!verifyAdmin(request, env)) return errorResponse('Unauthorized', 401)

        const body = await request.json().catch(() => ({}))
        const { key_code, reason } = body

        if (!key_code) {
          return errorResponse('Missing key_code parameter', 400)
        }

        const normalizedKey = key_code.trim().toUpperCase()
        const existing = await env.DB.prepare('SELECT * FROM supporter_keys WHERE key_code = ?').bind(normalizedKey).first()
        if (!existing) {
          return errorResponse('Key không tồn tại', 404)
        }

        const revokeReason = reason || 'Thu hồi bởi quản trị viên'
        await env.DB.prepare(`
          UPDATE supporter_keys
          SET is_blocked = 1, revoke_reason = ?
          WHERE key_code = ?
        `).bind(revokeReason, normalizedKey).run()

        return jsonResponse({
          success: true,
          message: 'Đã khóa và thu hồi key thành công.',
          key_code: normalizedKey,
          reason: revokeReason,
        })
      }

      if (pathname === '/redeem' && request.method === 'POST') {
        const body = await request.json().catch(() => ({}))
        const { key_code, hwid, uuid } = body

        if (!key_code || !hwid) {
          return errorResponse('Vui lòng cung cấp đầy đủ key_code và hwid', 400)
        }

        const normalizedKey = key_code.trim().toUpperCase()
        const normalizedHwid = hwid.trim().toLowerCase()

        const row = await env.DB.prepare('SELECT * FROM supporter_keys WHERE key_code = ?').bind(normalizedKey).first()
        if (!row) {
          return errorResponse('Mã Supporter Key không tồn tại hoặc không chính xác', 404)
        }

        if (row.is_blocked) {
          return errorResponse(`Key đã bị thu hồi: ${row.revoke_reason || 'Vi phạm chính sách'}`, 403, {
            revoked: true,
            reason: row.revoke_reason,
          })
        }

        if (!row.is_used) {
          await env.DB.prepare(`
            UPDATE supporter_keys
            SET is_used = 1, bound_hwid = ?, bound_to_uuid = ?, redeemed_at = CURRENT_TIMESTAMP
            WHERE key_code = ?
          `).bind(normalizedHwid, uuid || null, normalizedKey).run()

          return jsonResponse({
            valid: true,
            badge: row.tier || 'supporter',
            discord_id: row.discord_id,
            redeemed_at: new Date().toISOString(),
            key_code: normalizedKey,
            bound_hwid: normalizedHwid,
          })
        }

        if (row.bound_hwid === normalizedHwid || !row.bound_hwid) {
          if (!row.bound_hwid) {
            await env.DB.prepare(`
              UPDATE supporter_keys
              SET bound_hwid = ?, bound_to_uuid = COALESCE(?, bound_to_uuid)
              WHERE key_code = ?
            `).bind(normalizedHwid, uuid || null, normalizedKey).run()
          }

          return jsonResponse({
            valid: true,
            badge: row.tier || 'supporter',
            discord_id: row.discord_id,
            redeemed_at: row.redeemed_at || new Date().toISOString(),
            key_code: normalizedKey,
            bound_hwid: normalizedHwid,
          })
        }

        return errorResponse(
          'Key này đã được kích hoạt trên một máy tính khác. Để chuyển thiết bị, vui lòng dùng tính năng Reset HWID trên Discord Bot.',
          403,
          { hwid_mismatch: true }
        )
      }

      if ((pathname === '/verify' || pathname === '/status') && request.method === 'POST') {
        const body = await request.json().catch(() => ({}))
        const { key_code, hwid } = body

        if (!key_code || !hwid) {
          return errorResponse('Missing key_code or hwid', 400)
        }

        const normalizedKey = key_code.trim().toUpperCase()
        const normalizedHwid = hwid.trim().toLowerCase()

        const row = await env.DB.prepare('SELECT * FROM supporter_keys WHERE key_code = ?').bind(normalizedKey).first()
        if (!row) {
          return errorResponse('Key không tồn tại', 404)
        }

        if (row.is_blocked) {
          return jsonResponse({
            valid: false,
            revoked: true,
            reason: row.revoke_reason || 'Key đã bị thu hồi bởi quản trị viên',
          }, 200)
        }

        if (row.bound_hwid && row.bound_hwid !== normalizedHwid) {
          return jsonResponse({
            valid: false,
            hwid_mismatch: true,
            error: 'Thiết bị không trùng khớp với đăng ký ban đầu',
          }, 200)
        }

        return jsonResponse({
          valid: true,
          active: true,
          badge: row.tier || 'supporter',
          discord_id: row.discord_id,
          redeemed_at: row.redeemed_at,
        })
      }

      return jsonResponse({ service: 'PhantomX Supporter API', status: 'healthy', version: '2.1.0' })
    } catch (err) {
      return errorResponse(`Server Error: ${err.message}`, 500)
    }
  },
}

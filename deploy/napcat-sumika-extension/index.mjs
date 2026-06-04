let logger = null;
let installed = false;
const customActions = new Map();

function ok(data, echo = null) {
  return {
    status: "ok",
    retcode: 0,
    data,
    message: "",
    wording: "",
    echo,
    stream: "normal-action"
  };
}

function failed(error, echo = null, retcode = 1200) {
  const message = error?.message || String(error || "unknown error");
  return {
    status: "failed",
    retcode,
    data: null,
    message,
    wording: message,
    echo,
    stream: "normal-action"
  };
}

function createAction(actionName, handler) {
  async function run(payload, echo) {
    try {
      const data = await handler(payload || {});
      return ok(data, echo);
    } catch (error) {
      logger?.error(`${actionName} failed:`, error);
      return failed(error, echo);
    }
  }
  return {
    actionName,
    actionSummary: `Sumika custom action: ${actionName}`,
    async websocketHandle(payload, echo) {
      return await run(payload, echo);
    },
    async handle(payload, _adapter, _config, _req, echo) {
      return await run(payload, echo);
    }
  };
}

function ownFunctionNames(value) {
  const names = new Set();
  let cursor = value;
  for (let depth = 0; cursor && depth < 8; depth += 1) {
    for (const key of Reflect.ownKeys(cursor)) {
      if (key === "constructor") continue;
      let descriptor;
      try {
        descriptor = Object.getOwnPropertyDescriptor(cursor, key);
      } catch {
        continue;
      }
      if (typeof descriptor?.value === "function") names.add(String(key));
    }
    cursor = Object.getPrototypeOf(cursor);
  }
  return Array.from(names).sort();
}

function ownKeys(value) {
  const keys = new Set();
  let cursor = value;
  for (let depth = 0; cursor && depth < 8; depth += 1) {
    for (const key of Reflect.ownKeys(cursor)) keys.add(String(key));
    cursor = Object.getPrototypeOf(cursor);
  }
  return Array.from(keys).sort();
}

async function toUid(ctx, userId) {
  const uin = String(userId || "").trim();
  if (!/^\d+$/.test(uin)) throw new Error("user_id must be numeric");
  let uid = await ctx.core.apis.UserApi.getUidByUinV2(uin);
  if (!uid || String(uid) === "0") {
    try {
      const detail = await ctx.core.apis.UserApi.getUserDetailInfoByUin(uin);
      uid = detail?.detail?.uid || detail?.uid || "";
    } catch (error) {
      logger?.warn(`getUserDetailInfoByUin failed for ${uin}:`, error);
    }
  }
  return { uin, uid: uid && String(uid) !== "0" ? String(uid) : "" };
}

async function callServiceMethod(service, method, args) {
  if (typeof service?.[method] !== "function") {
    throw new Error(`BuddyService method not available: ${method}`);
  }
  return await service[method](...args);
}

function buildFriendRequestArgs(method, uid, uin, comment, remark, source) {
  const text = comment || "";
  const mark = remark || "";
  const scene = Number.isFinite(Number(source)) ? Number(source) : 0;
  const id = uid || uin;
  const requestObjects = [
    { uid: id, uin, friendUid: id, verifyInfo: text, msg: text, source: scene, remark: mark },
    { friendUid: id, verifyInfo: text, source: scene, remark: mark },
    { uid: id, verifyInfo: text, source: scene, remark: mark },
    { uin, verifyInfo: text, source: scene, remark: mark },
    { friendUid: id, msg: text, source: scene },
    { uid: id, msg: text, source: scene },
    { uin, msg: text, source: scene },
    { friendUid: id, source: scene },
    { uid: id, source: scene },
    { uin, source: scene }
  ];
  const batchObjects = [
    { friendUids: [id], verifyInfo: text, msg: text, source: scene, remark: mark },
    { uidList: [id], verifyInfo: text, msg: text, source: scene, remark: mark },
    { uids: [id], verifyInfo: text, msg: text, source: scene, remark: mark },
    { uinList: [uin], verifyInfo: text, msg: text, source: scene, remark: mark },
    { uins: [uin], verifyInfo: text, msg: text, source: scene, remark: mark }
  ];
  const lower = method.toLowerCase();
  if (lower.includes("byuin")) {
    return [[uin, text, scene], [uin, text], [uin]];
  }
  if (lower.includes("uid")) {
    return [[id, text, scene], [id, text], [id]];
  }
  return [
    ...batchObjects.map((item) => [item]),
    ...requestObjects.map((item) => [[item]]),
    ...batchObjects.map((item) => [[item]]),
    ...requestObjects.map((item) => [item]),
    [id, text, scene],
    [id, text],
    [id],
    [uin, text, scene],
    [uin, text],
    [uin]
  ];
}

function lowLevelResultOk(result) {
  if (!result || typeof result !== "object") return true;
  if (!Object.prototype.hasOwnProperty.call(result, "result")) return true;
  return Number(result.result) === 0;
}

function lowLevelErrorMessage(result) {
  if (!result || typeof result !== "object") return String(result);
  return `result=${result.result}, errMsg=${result.errMsg || ""}`;
}

async function tryAddFriend(ctx, payload) {
  const { uin, uid } = await toUid(ctx, payload.user_id);
  const isFriend = uid ? await ctx.core.apis.FriendApi.isBuddy(uid) : false;
  if (isFriend) return { status: "already_friend", user_id: uin, uid };

  const service = ctx.core.context.session.getBuddyService();
  const explicitMethod = payload.method ? String(payload.method) : "";
  const methods = explicitMethod
    ? [explicitMethod]
    : [
        "reqToAddFriends",
        "addBuddy",
        "addFriend",
        "addBuddyReq",
        "sendBuddyReq",
        "sendBuddyRequest",
        "requestAddBuddy",
        "requestAddFriend",
        "applyBuddy",
        "applyFriend",
        "addBuddyWithVerify",
        "addBuddyWithVerifyInfo",
        "addFriendWithVerify"
      ];
  const errors = [];
  for (const method of methods) {
    const argVariants = buildFriendRequestArgs(
      method,
      uid,
      uin,
      String(payload.comment || ""),
      String(payload.remark || ""),
      payload.source
    );
    for (const args of argVariants) {
      try {
        const result = await callServiceMethod(service, method, args);
        if (!lowLevelResultOk(result)) {
          errors.push({
            method,
            args_shape: args.map((arg) => (typeof arg === "object" ? Object.keys(arg) : typeof arg)),
            error: lowLevelErrorMessage(result),
            result
          });
          continue;
        }
        return {
          status: "request_sent_or_accepted",
          user_id: uin,
          uid: uid || null,
          method,
          args_shape: args.map((arg) => (typeof arg === "object" ? Object.keys(arg) : typeof arg)),
          result
        };
      } catch (error) {
        errors.push({
          method,
          args_shape: args.map((arg) => (typeof arg === "object" ? Object.keys(arg) : typeof arg)),
          error: error?.message || String(error)
        });
        if (explicitMethod) break;
      }
    }
  }
  return {
    status: "no_candidate_succeeded",
    user_id: uin,
    uid: uid || null,
    available_buddy_methods: ownFunctionNames(service),
    errors: errors.slice(0, 12)
  };
}

async function setAvatarVerbose(ctx, payload) {
  const file = String(payload.file || "").trim();
  if (!file) throw new Error("file required");
  const result = await ctx.actions.call("set_qq_avatar", { file }, ctx.adapterName, ctx.pluginManager.config);
  return { result };
}

async function callBuddyService(ctx, payload) {
  const method = String(payload.method || "").trim();
  if (!method) throw new Error("method required");
  const args = Array.isArray(payload.args) ? payload.args : [];
  const service = ctx.core.context.session.getBuddyService();
  const result = await callServiceMethod(service, method, args);
  return { method, result };
}

async function callProfileService(ctx, payload) {
  const method = String(payload.method || "").trim();
  if (!method) throw new Error("method required");
  const args = Array.isArray(payload.args) ? payload.args : [];
  const service = ctx.core.context.session.getProfileService();
  const result = await callServiceMethod(service, method, args);
  return { method, result };
}

function methodInfo(service, method) {
  const fn = service?.[method];
  if (typeof fn !== "function") return null;
  const source = String(fn);
  return {
    name: method,
    length: fn.length,
    source: source.length > 1000 ? source.slice(0, 1000) + `... <${source.length} chars>` : source
  };
}

function installActionPatch(ctx) {
  if (installed) return;
  const originalGet = ctx.actions.get.bind(ctx.actions);
  const originalCall = ctx.actions.call.bind(ctx.actions);
  ctx.actions.get = (actionName) => {
    if (customActions.has(actionName)) return customActions.get(actionName);
    return originalGet(actionName);
  };
  ctx.actions.call = async (actionName, params, adapter, config) => {
    const action = customActions.get(actionName);
    if (!action) return await originalCall(actionName, params, adapter, config);
    const result = await action.handle(params, adapter, config);
    if (result.status !== "ok") {
      throw new Error(result.message || `Action ${String(actionName)} failed`);
    }
    return result.data;
  };
  installed = true;
}

const plugin_init = async (ctx) => {
  logger = ctx.logger;
  installActionPatch(ctx);
  customActions.set(
    "sumika_debug_buddy_service",
    createAction("sumika_debug_buddy_service", async (payload) => {
      const service = ctx.core.context.session.getBuddyService();
      const inspectMethod = payload.method ? String(payload.method) : "";
      return {
        action_count: customActions.size,
        service_type: service?.constructor?.name || typeof service,
        keys: ownKeys(service),
        functions: ownFunctionNames(service),
        method_info: inspectMethod ? methodInfo(service, inspectMethod) : null,
        friend_api_functions: ownFunctionNames(ctx.core.apis.FriendApi),
        user_api_functions: ownFunctionNames(ctx.core.apis.UserApi)
      };
    })
  );
  customActions.set(
    "sumika_add_friend",
    createAction("sumika_add_friend", async (payload) => await tryAddFriend(ctx, payload))
  );
  customActions.set(
    "sumika_set_avatar_verbose",
    createAction("sumika_set_avatar_verbose", async (payload) => await setAvatarVerbose(ctx, payload))
  );
  customActions.set(
    "sumika_call_buddy_service",
    createAction("sumika_call_buddy_service", async (payload) => await callBuddyService(ctx, payload))
  );
  customActions.set(
    "sumika_debug_profile_service",
    createAction("sumika_debug_profile_service", async (payload) => {
      const service = ctx.core.context.session.getProfileService();
      const inspectMethod = payload.method ? String(payload.method) : "";
      return {
        service_type: service?.constructor?.name || typeof service,
        keys: ownKeys(service),
        functions: ownFunctionNames(service),
        method_info: inspectMethod ? methodInfo(service, inspectMethod) : null
      };
    })
  );
  customActions.set(
    "sumika_call_profile_service",
    createAction("sumika_call_profile_service", async (payload) => await callProfileService(ctx, payload))
  );
  logger?.info(`Sumika extension loaded, custom actions: ${Array.from(customActions.keys()).join(", ")}`);
};

const plugin_cleanup = async () => {
  logger?.info("Sumika extension cleanup");
};

export { plugin_cleanup, plugin_init };

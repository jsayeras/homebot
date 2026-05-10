import asyncio
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from bot.config import Config
from services.docker_service import DockerService
from services.info_service import InfoService
from services.opencode_service import OpenCodeService
from services.tunnel_service import TunnelService
from services.webhook_service import configure as configure_webhook, run_fastapi


class BotApp:

    def __init__(self) -> None:
        self.config = Config()
        self.info_service = InfoService()
        self.seen_chats: set[int] = set()
        self.tunnel_service = TunnelService()
        self.opencode_service = OpenCodeService()
        self.docker_service = DockerService(self.config.SERVICES_YAML, self.config.DOCKER_HOST)

    def _make_keyboard(self) -> InlineKeyboardMarkup:
        keyboard = [
            [
                InlineKeyboardButton("Info", callback_data="get_info"),
                InlineKeyboardButton("Sync DuckDNS", callback_data="sync_duckdns"),
                InlineKeyboardButton("OpenCode", callback_data="manage_opencode"),
            ],
            [
                InlineKeyboardButton("Manage Tunnels", callback_data="manage_tunnels"),
                InlineKeyboardButton("Manage Services", callback_data="manage_services"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        reply_markup = self._make_keyboard()
        await update.message.reply_text("Press the button:", reply_markup=reply_markup)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("hello world")

    async def get_info_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        chat_id = update.effective_chat.id
        await query.edit_message_text("Fetching info...")

        ip = await self.info_service.get_current_ip()
        addresses = await self.info_service.resolve_domain("saydu.duckdns.org")

        lines = [
            f"🌐 IP: {ip}",
            f"📡 DNS: saydu.duckdns.org → {addresses}",
        ]
        for tname, tinfo in self.tunnel_service.running.items():
            url = tinfo.url or "waiting..."
            lines.append(f"🚇 {tname}: <a href=\"{url}\">{url}</a>")

        await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="HTML",
        )

    async def manage_opencode_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        keyboard = []
        if self.opencode_service.running:
            url = self.opencode_service.url or "unknown"
            keyboard.append([InlineKeyboardButton(f"✅ Running — {url}", callback_data="noop")])
            keyboard.append([InlineKeyboardButton("🛑 Stop", callback_data="opencode_stop")])
        else:
            keyboard.append([InlineKeyboardButton("▶️ Start", callback_data="opencode_start")])
        keyboard.append([InlineKeyboardButton("Back", callback_data="back_main")])
        await query.edit_message_text("OpenCode:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def opencode_start_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Starting OpenCode...")
        result = await self.opencode_service.start()
        reply_markup = self._make_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result, reply_markup=reply_markup)

    async def opencode_stop_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Stopping OpenCode...")
        result = await self.opencode_service.stop()
        reply_markup = self._make_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result, reply_markup=reply_markup)

    async def sync_duckdns_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Syncing DuckDNS...")

        result = await self.info_service.sync_duckdns(
            self.config.DUCKDNS_DOMAIN, self.config.DUCKDNS_TOKEN
        )
        await query.edit_message_text(result)

    async def manage_tunnels_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        services = self.docker_service.services
        tunnel_services = {n: s for n, s in services.items() if s.get("tunnel")}
        running_tunnels = self.tunnel_service.running

        keyboard = []
        for name, svc in tunnel_services.items():
            addr = svc["tunnel"]
            is_running = name in running_tunnels
            status = " ✅" if is_running else ""
            keyboard.append([InlineKeyboardButton(f"{name} ({addr}){status}", callback_data=f"tunnel_svc_start:{name}")])
            actions = []
            if is_running:
                actions.append(InlineKeyboardButton("🛑", callback_data=f"tunnel_svc_stop:{name}"))
            actions.append(InlineKeyboardButton("✏️", callback_data=f"tunnel_svc_edit:{name}"))
            actions.append(InlineKeyboardButton("🗑️", callback_data=f"tunnel_svc_del:{name}"))
            keyboard.append(actions)

        manual = {n: t for n, t in running_tunnels.items() if n not in tunnel_services}
        for name, info in manual.items():
            url = info.url or "waiting..."
            keyboard.append([InlineKeyboardButton(f"{name} → {url} ✅", callback_data="noop")])
            keyboard.append([InlineKeyboardButton("🛑", callback_data=f"stop_tunnel:{name}")])

        keyboard.append([InlineKeyboardButton("Start Manual Tunnel", callback_data="start_tunnel")])
        if running_tunnels:
            keyboard.append([InlineKeyboardButton("Stop All", callback_data="stop_tunnel:__all__")])
        keyboard.append([InlineKeyboardButton("Back", callback_data="back_main")])
        await query.edit_message_text("Manage tunnels:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def tunnel_svc_start_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        addr = self.docker_service.get_tunnel_addr(name)
        if not addr:
            await query.edit_message_text(f"No tunnel configured for {name}.")
            return

        host, port_str = addr.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            await query.edit_message_text(f"Invalid tunnel address: {addr}")
            return

        await query.edit_message_text(f"Starting tunnel for <code>{name}</code>...", parse_mode="HTML")
        result = await self.tunnel_service.start(name=name, host=host, port=port)
        reply_markup = self._make_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚇 {result}", reply_markup=reply_markup)

    async def tunnel_svc_stop_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        await query.edit_message_text(f"Stopping tunnel for <code>{name}</code>...", parse_mode="HTML")
        result = await self.tunnel_service.stop(name)
        reply_markup = self._make_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result, reply_markup=reply_markup)

    async def tunnel_svc_edit_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        current = self.docker_service.get_tunnel_addr(name) or ""
        context.user_data["editing_tunnel"] = name
        keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_tunnel_edit")]]
        await query.edit_message_text(
            f"✏️ New tunnel address for <code>{name}</code>:\nCurrent: <code>{current}</code>\n\nSend <code>host:port</code> or leave empty to clear:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def tunnel_svc_del_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        if name in self.tunnel_service.running:
            await self.tunnel_service.stop(name)
        result = self.docker_service.delete_tunnel(name)
        reply_markup = self._make_keyboard()
        await query.edit_message_text(result, reply_markup=reply_markup)

    async def cancel_tunnel_edit_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        context.user_data.pop("editing_tunnel", None)
        reply_markup = self._make_keyboard()
        await query.edit_message_text("Edit cancelled.", reply_markup=reply_markup)

    async def handle_tunnel_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        name = context.user_data.pop("editing_tunnel", None)
        if name is None:
            return
        new_addr = update.message.text.strip()
        result = self.docker_service.edit_tunnel(name, new_addr)
        reply_markup = self._make_keyboard()
        await update.message.reply_text(result, reply_markup=reply_markup)

    async def start_tunnel_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        context.user_data["awaiting_tunnel_addr"] = True
        await query.edit_message_text(
            "Send me <code>name host:port</code> for the tunnel, e.g.\n<code>webapp localhost:3000</code> or <code>api 192.168.1.10:8080</code>",
            parse_mode="HTML",
        )

    async def stop_tunnel_exec_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        if name == "__all__":
            result = await self.tunnel_service.stop_all()
        else:
            result = await self.tunnel_service.stop(name)
        reply_markup = self._make_keyboard()
        await query.edit_message_text(result, reply_markup=reply_markup)

    async def manage_services_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        services = self.docker_service.services
        if not services:
            await query.edit_message_text("No services defined in config.")
            return

        self.docker_service.load()
        running = await self.docker_service.running_set()
        all_containers = await self.docker_service.all_containers_set()
        keyboard = []
        for name in services:
            status = " ✅" if name in running else ""
            has_tunnel = " 🚇" if name in self.tunnel_service.running else ""
            keyboard.append([InlineKeyboardButton(f"{name}{has_tunnel}{status}", callback_data=f"run_container:{name}")])
            actions = []
            if name in running:
                actions.append(InlineKeyboardButton("🛑", callback_data=f"stop_container:{name}"))
            elif name in all_containers:
                actions.append(InlineKeyboardButton("🧹", callback_data=f"clean_container:{name}"))
            actions.append(InlineKeyboardButton("✏️", callback_data=f"edit_container:{name}"))
            actions.append(InlineKeyboardButton("🗑️", callback_data=f"delete_container:{name}"))
            keyboard.append(actions)
        keyboard.append([InlineKeyboardButton("Back", callback_data="back_main")])
        await query.edit_message_text("Manage services:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def run_container_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        await query.edit_message_text(f"Starting <code>{name}</code>...", parse_mode="HTML")

        result = await self.docker_service.run(name)

        tunnel_addr = self.docker_service.get_tunnel_addr(name)
        if tunnel_addr:
            host, port_str = tunnel_addr.rsplit(":", 1)
            try:
                port = int(port_str)
                tunnel_result = await self.tunnel_service.start(name=name, host=host, port=port)
                result += f"\n🚇 Tunnel: {tunnel_result}"
            except (ValueError, Exception) as e:
                result += f"\n🚇 Tunnel error: {e}"

        reply_markup = self._make_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result, reply_markup=reply_markup)

    async def stop_container_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        await query.edit_message_text(f"Stopping <code>{name}</code>...", parse_mode="HTML")
        result = await self.docker_service.stop(name)
        reply_markup = self._make_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result, reply_markup=reply_markup)

    async def edit_container_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        self.docker_service.load()
        svc = self.docker_service.services.get(name, {})
        command = svc.get("command", "")
        tunnel = svc.get("tunnel", "")
        context.user_data["editing_container"] = name
        keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_edit")]]
        text = f"✏️ Editing <code>{name}</code>\n\nCommand:\n<code>{command}</code>"
        if tunnel:
            text += f"\nTunnel: {tunnel}"
        text += "\n\nSend the new docker run params:"
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def cancel_edit_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        context.user_data.pop("editing_container", None)
        reply_markup = self._make_keyboard()
        await query.edit_message_text("Edit cancelled.", reply_markup=reply_markup)

    async def delete_container_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        running = await self.docker_service.running_set()
        msgs = []
        if name in running:
            process = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await process.communicate()
            msgs.append(f"Force-removed running container.")
        result = self.docker_service.delete(name)
        msgs.append(result)
        reply_markup = self._make_keyboard()
        await query.edit_message_text("\n".join(msgs), reply_markup=reply_markup)

    async def clean_container_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()

        name = query.data.split(":", 1)[1]
        await query.edit_message_text(f"Cleaning <code>{name}</code>...", parse_mode="HTML")
        result = await self.docker_service.clean(name)
        reply_markup = self._make_keyboard()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result, reply_markup=reply_markup)

    async def handle_container_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        name = context.user_data.pop("editing_container", None)
        if name is None:
            return
        new_params = update.message.text.strip()
        result = self.docker_service.edit(name, new_params)
        tunnel = self.docker_service.get_tunnel_addr(name)
        if tunnel:
            result += f"\n🚇 Tunnel: {tunnel}"
        reply_markup = self._make_keyboard()
        await update.message.reply_text(result, reply_markup=reply_markup)

    async def back_main_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        query = update.callback_query
        await query.answer()
        reply_markup = self._make_keyboard()
        await query.edit_message_text("Press the button:", reply_markup=reply_markup)

    async def handle_tunnel_addr(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        if not context.user_data.pop("awaiting_tunnel_addr", False):
            return
        parts = update.message.text.strip().split(None, 1)
        if len(parts) != 2 or ":" not in parts[1]:
            await update.message.reply_text(
                "Invalid format. Use <code>name host:port</code> e.g.\n<code>webapp localhost:3000</code>",
                parse_mode="HTML",
            )
            context.user_data["awaiting_tunnel_addr"] = True
            return
        name = parts[0]
        host, port_str = parts[1].rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            await update.message.reply_text("Invalid port. Use <code>name host:port</code>", parse_mode="HTML")
            context.user_data["awaiting_tunnel_addr"] = True
            return
        await update.message.reply_text("Starting tunnel...")
        result = await self.tunnel_service.start(name=name, host=host, port=port)
        reply_markup = self._make_keyboard()
        await update.message.reply_text(f"Tunnel URL: {result}", reply_markup=reply_markup)

    async def log_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if chat_id not in self.seen_chats:
            self.seen_chats.add(chat_id)
            print(f"New chat: {chat_id}")
        if chat_id == self.config.ALLOWED_CHAT_ID and update.message and not update.edited_message:
            reply_markup = self._make_keyboard()
            await update.message.reply_text("Press the button:", reply_markup=reply_markup)

    async def chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self.config.ALLOWED_CHAT_ID:
            return
        lines = "\n".join(str(c) for c in sorted(self.seen_chats))
        await update.message.reply_text(f"Seen chats:\n{lines}" if lines else "No chats yet.")

    def run(self) -> None:
        configure_webhook(self.config.TELEGRAM_BOT_TOKEN, self.config.ALLOWED_CHAT_ID, self.config.WEBHOOK_SECRET)
        t = threading.Thread(target=run_fastapi, daemon=True)
        t.start()

        token = self.config.TELEGRAM_BOT_TOKEN
        application = Application.builder().token(token).build()
        app = self
        application.add_handler(CommandHandler("start", app.start))
        application.add_handler(CallbackQueryHandler(app.button_callback, pattern="^month_status$"))
        application.add_handler(CallbackQueryHandler(app.get_info_callback, pattern="^get_info$"))
        application.add_handler(CallbackQueryHandler(app.sync_duckdns_callback, pattern="^sync_duckdns$"))
        application.add_handler(CallbackQueryHandler(app.manage_opencode_callback, pattern="^manage_opencode$"))
        application.add_handler(CallbackQueryHandler(app.opencode_start_callback, pattern="^opencode_start$"))
        application.add_handler(CallbackQueryHandler(app.opencode_stop_callback, pattern="^opencode_stop$"))
        application.add_handler(CallbackQueryHandler(app.manage_tunnels_callback, pattern="^manage_tunnels$"))
        application.add_handler(CallbackQueryHandler(app.tunnel_svc_start_callback, pattern="^tunnel_svc_start:"))
        application.add_handler(CallbackQueryHandler(app.tunnel_svc_stop_callback, pattern="^tunnel_svc_stop:"))
        application.add_handler(CallbackQueryHandler(app.tunnel_svc_edit_callback, pattern="^tunnel_svc_edit:"))
        application.add_handler(CallbackQueryHandler(app.tunnel_svc_del_callback, pattern="^tunnel_svc_del:"))
        application.add_handler(CallbackQueryHandler(app.cancel_tunnel_edit_callback, pattern="^cancel_tunnel_edit$"))
        application.add_handler(CallbackQueryHandler(app.start_tunnel_callback, pattern="^start_tunnel$"))
        application.add_handler(CallbackQueryHandler(app.stop_tunnel_exec_callback, pattern="^stop_tunnel:"))
        application.add_handler(CallbackQueryHandler(app.back_main_callback, pattern="^noop$"))
        application.add_handler(CallbackQueryHandler(app.manage_services_callback, pattern="^manage_services$"))
        application.add_handler(CallbackQueryHandler(app.run_container_callback, pattern="^run_container:"))
        application.add_handler(CallbackQueryHandler(app.stop_container_callback, pattern="^stop_container:"))
        application.add_handler(CallbackQueryHandler(app.edit_container_callback, pattern="^edit_container:"))
        application.add_handler(CallbackQueryHandler(app.cancel_edit_callback, pattern="^cancel_edit$"))
        application.add_handler(CallbackQueryHandler(app.clean_container_callback, pattern="^clean_container:"))
        application.add_handler(CallbackQueryHandler(app.delete_container_callback, pattern="^delete_container:"))
        application.add_handler(CallbackQueryHandler(app.back_main_callback, pattern="^back_main$"))
        application.add_handler(CommandHandler("chats", app.chats))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, app.handle_tunnel_addr))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, app.handle_container_edit))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, app.handle_tunnel_edit))
        application.add_handler(MessageHandler(filters.ALL, app.log_chat), group=-1)
        application.run_polling(allowed_updates=Update.ALL_TYPES)

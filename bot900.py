import logging
import random
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv
load_dotenv()  # Загружает переменные из .env
env_path = r"C:\Users\aleks\Desktop\bot\.env"
TOKEN = os.getenv("TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_ID = os.getenv("ADMIN_ID")
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


chat_links = {
    "Основной чат": "https://t.me/+w6IB3NeDijtlNjkyt",
    "Дополнительный ресурс": "https://t.me/your_secondary_chat"
}
chat_ids = set()
current_delay_range = (25, 30)  # в минутах, минимум 1 минута
current_message = """Здравствуйте!  
Я — бот-ассистент этого канала. Приглашаю вас присоединиться к нашему дополнительному ресурсу, где вы найдёте ещё больше полезной информации и эксклюзивных материалов.  
Переходите по ссылке ниже, чтобы быть в курсе самых актуальных новостей. Спасибо, что вы с нами!

https://t.me/+w6IB3NeDijtlNjky

Для уточнения информации пишите @borz_911"""
is_sending_active = False

# Чтобы избежать дублирования задач рассылки
job_sending = None


def create_keyboard(buttons, back_button=True):
    if not buttons:
        buttons = []
    elif not isinstance(buttons[0], list):
        buttons = [buttons]
    if back_button:
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data='back')])
    return InlineKeyboardMarkup(buttons)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Главное меню:"):
    keyboard = [
        [InlineKeyboardButton("🔗 Получить ссылки на чаты", callback_data='get_chat_links')]
    ]
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data='admin_panel')])
    reply_markup = create_keyboard(keyboard, back_button=False)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)


async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("Доступ запрещен", show_alert=True)
        return

    sending_status = "✅ Включена" if is_sending_active else "❌ Выключена"
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить сообщение", callback_data='edit_message')],
        [InlineKeyboardButton("⏱ Изменить задержку", callback_data='edit_delay')],
        [InlineKeyboardButton("➕ Добавить чат (пересланное сообщение)", callback_data='add_chat')],
        [InlineKeyboardButton("➕ Добавить чат вручную (ID или ссылка)", callback_data='add_chat_manual')],
        [InlineKeyboardButton("📋 Список чатов для рассылки", callback_data='list_chats')],
        [InlineKeyboardButton("🔗 Управление ссылками", callback_data='manage_links')],
        [InlineKeyboardButton(f"🔄 Рассылка: {sending_status}", callback_data='toggle_sending')]
    ]
    await update.callback_query.edit_message_text("Админ-панель:", reply_markup=create_keyboard(keyboard))


async def show_links_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = [
        [InlineKeyboardButton("➕ Добавить ссылку", callback_data='add_link')],
        [InlineKeyboardButton("➖ Удалить ссылку", callback_data='remove_link')],
        [InlineKeyboardButton("📋 Просмотр ссылок", callback_data='view_links')]
    ]
    await update.callback_query.edit_message_text("Управление ссылками:", reply_markup=create_keyboard(keyboard))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    if not context.args or context.args[0] != ADMIN_PASSWORD:
        await update.message.reply_text("Неверный пароль")
        return
    ADMIN_ID = update.effective_user.id
    context.user_data['admin_authenticated'] = True
    await update.message.reply_text(f"✅ Вы вошли как админ (ID: {ADMIN_ID})")
    await show_main_menu(update, context)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_sending_active, job_sending

    query = update.callback_query
    await query.answer()
    try:
        if query.data == 'back':
            await show_main_menu(update, context)
        elif query.data == 'get_chat_links':
            if not chat_links:
                await query.edit_message_text("Нет доступных чатов")
            else:
                keyboard = [[InlineKeyboardButton(name, url=link)] for name, link in chat_links.items()]
                await query.edit_message_text("Выберите чат:", reply_markup=create_keyboard(keyboard, back_button=True))
        elif query.data == 'admin_panel':
            await show_admin_panel(update, context)
        elif query.data == 'add_chat':
            context.user_data['awaiting_chat'] = True
            await query.edit_message_text("Перешлите сообщение из чата или канала, куда нужно добавить рассылку:", reply_markup=create_keyboard([]))
        elif query.data == 'add_chat_manual':
            context.user_data['awaiting_chat_manual'] = True
            await query.edit_message_text("Отправьте ID чата (например, -1001234567890) или ссылку (например, https://t.me/username):", reply_markup=create_keyboard([]))
        elif query.data == 'list_chats':
            if not chat_ids:
                await query.edit_message_text("Нет чатов для рассылки")
            else:
                text = "\n".join([f"ID: {cid}" for cid in chat_ids])
                await query.edit_message_text(f"Чаты для рассылки:\n{text}")
        elif query.data == 'edit_message':
            context.user_data['editing_message'] = True
            await query.edit_message_text(f"Текущее сообщение:\n\n{current_message}\n\nОтправьте новое сообщение:", reply_markup=create_keyboard([]))
        elif query.data == 'edit_delay':
            context.user_data['editing_delay'] = True
            await query.edit_message_text(f"Текущая задержка: {current_delay_range[0]}-{current_delay_range[1]} мин\nОтправьте новую задержку (например, '1 2'):", reply_markup=create_keyboard([]))
        elif query.data == 'toggle_sending':
            is_sending_active = not is_sending_active
            await show_admin_panel(update, context)
            logger.info(f"Рассылка {'включена' if is_sending_active else 'выключена'}")

            if is_sending_active:
                # Отменяем предыдущую задачу рассылки, если она есть
                if job_sending:
                    job_sending.schedule_removal()
                    job_sending = None
                # Запускаем рассылку через секунду
                job_sending = context.job_queue.run_once(send_messages, 1)
        elif query.data == 'manage_links':
            await show_links_menu(update, context)
        elif query.data == 'add_link':
            context.user_data['adding_link'] = True
            await query.edit_message_text("Отправьте название и ссылку в формате:\nНазвание|ссылка", reply_markup=create_keyboard([]))
        elif query.data == 'remove_link':
            if not chat_links:
                await query.edit_message_text("Нет ссылок для удаления")
            else:
                keyboard = [[InlineKeyboardButton(name, callback_data=f'remove_{name}')] for name in chat_links]
                await query.edit_message_text("Выберите ссылку для удаления:", reply_markup=create_keyboard(keyboard))
        elif query.data == 'view_links':
            if not chat_links:
                await query.edit_message_text("Нет сохраненных ссылок")
            else:
                links_text = "\n".join([f"{name}: {link}" for name, link in chat_links.items()])
                await query.edit_message_text(f"Сохраненные ссылки:\n\n{links_text}", reply_markup=create_keyboard([]))
        elif query.data.startswith('remove_'):
            link_name = query.data[7:]
            if link_name in chat_links:
                del chat_links[link_name]
                await query.edit_message_text(f"Ссылка '{link_name}' удалена", reply_markup=create_keyboard([]))
            else:
                await query.answer("Ссылка не найдена", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.answer("Произошла ошибка!", show_alert=True)


async def handle_forwarded_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("⚙️ Перехвачено пересланное сообщение!")
    logger.info(f"forward_from_chat: {update.message.forward_from_chat}")
    logger.info(f"sender_chat: {update.message.sender_chat}")
    logger.info(f"forward_from: {update.message.forward_from}")

    if not context.user_data.get('awaiting_chat') or update.effective_user.id != ADMIN_ID:
        return

    chat_info = update.message.forward_from_chat or update.message.sender_chat

    if chat_info:
        if chat_info.id not in chat_ids:
            chat_ids.add(chat_info.id)
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ Чат '{chat_info.title}' добавлен (ID: {chat_info.id})")
            logger.info(f"Добавлен чат: {chat_info.title} ({chat_info.id})")
        else:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"ℹ️ Чат '{chat_info.title}' уже добавлен.")
        context.user_data.pop('awaiting_chat', None)
    else:
        await update.message.reply_text("❌ Это сообщение не из канала/чата. Перешлите сообщение из группы или канала, а не от пользователя.")


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_message, current_delay_range

    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text.strip()

    if context.user_data.get('editing_message'):
        current_message = text
        await update.message.reply_text("✅ Сообщение обновлено!")
        context.user_data.pop('editing_message', None)

    elif context.user_data.get('editing_delay'):
        try:
            parts = text.split()
            if len(parts) != 2:
                raise ValueError("Неверное количество аргументов")
            min_d, max_d = map(int, parts)
            if min_d < 1 or max_d < 1:
                raise ValueError("Значения должны быть положительными")
            current_delay_range = (min(min_d, max_d), max(min_d, max_d))
            await update.message.reply_text(f"✅ Задержка обновлена: {current_delay_range[0]}-{current_delay_range[1]} мин")
        except Exception:
            await update.message.reply_text("❌ Формат неверный. Используйте: мин макс (положительные числа)")
        context.user_data.pop('editing_delay', None)

    elif context.user_data.get('adding_link'):
        try:
            name, link = text.split('|', 1)
            chat_links[name.strip()] = link.strip()
            await update.message.reply_text(f"✅ Ссылка '{name.strip()}' добавлена!")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Используйте: Название|ссылка")
        context.user_data.pop('adding_link', None)

    elif context.user_data.get('awaiting_chat_manual'):
        input_str = text
        chat = None
        try:
            if input_str.startswith("https://t.me/") or input_str.startswith("t.me/"):
                username = input_str.split('/')[-1]
                chat = await context.bot.get_chat(username)
            else:
                chat_id = int(input_str)
                chat = await context.bot.get_chat(chat_id)
        except Exception as e:
            await update.message.reply_text(f"❌ Не удалось получить информацию о чате:\n{e}")
            context.user_data.pop('awaiting_chat_manual', None)
            return

        if chat:
            if chat.id not in chat_ids:
                chat_ids.add(chat.id)
                await update.message.reply_text(f"✅ Чат '{chat.title}' добавлен (ID: {chat.id})")
                logger.info(f"Добавлен чат вручную: {chat.title} ({chat.id})")
            else:
                await update.message.reply_text(f"ℹ️ Чат '{chat.title}' уже добавлен.")
        else:
            await update.message.reply_text("❌ Не удалось добавить чат.")

        context.user_data.pop('awaiting_chat_manual', None)


async def send_messages(context: ContextTypes.DEFAULT_TYPE):
    global is_sending_active, job_sending

    logger.info("send_messages вызвана")

    if not is_sending_active:
        logger.info("Рассылка выключена — пропускаем отправку.")
        job_sending = None
        return

    logger.info(f"Начинаем рассылку в {len(chat_ids)} чат(ов).")

    remove_ids = set()
    for chat_id in list(chat_ids):
        try:
            await context.bot.send_message(chat_id=chat_id, text=current_message, disable_web_page_preview=True)
            logger.info(f"Отправлено сообщение в чат {chat_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки в чат {chat_id}: {e}")
            # Удаляем чат из рассылки, если бот не имеет прав или чат удалён
            if "not enough rights" in str(e).lower() or "chat not found" in str(e).lower():
                remove_ids.add(chat_id)

    for cid in remove_ids:
        chat_ids.discard(cid)
        logger.info(f"Удалён чат из списка рассылки: {cid}")

    # Планируем следующую рассылку через задержку в секундах
    delay = random.randint(*current_delay_range) * 60
    logger.info(f"Следующая рассылка через {delay // 60} минут.")
    job_sending = context.job_queue.run_once(send_messages, delay)


def main():
    global job_sending

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_text))
    application.add_handler(MessageHandler(filters.FORWARDED, handle_forwarded_message))

    # Запускаем задачу рассылки через 5 секунд после старта (если is_sending_active=True)
    def start_sending_job(context):
        global job_sending
        if is_sending_active:
            job_sending = context.job_queue.run_once(send_messages, 1)

    application.job_queue.run_once(start_sending_job, 5)

    application.run_polling()


if __name__ == '__main__':
    main()

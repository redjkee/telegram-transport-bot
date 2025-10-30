# bot.py (ФИНАЛЬНАЯ ПРОФЕССИОНАЛЬНАЯ ВЕРСИЯ 3.0)

import os
import logging
import pandas as pd
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler
)
from telegram.error import BadRequest
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from parser import process_excel_file

# --- Настройка ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

user_data = {}

# --- Состояния для диалогов (ConversationHandler) ---
(
    ASK_CAR_STATS, ASK_DRIVER_STATS,
    ASK_CAR_EXPORT, ASK_DRIVER_EXPORT
) = range(4)

# --- Клавиатуры ---
def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Общая статистика", callback_data='main_stats')],
        [InlineKeyboardButton("🚗 Статистика по гос. номеру", callback_data='main_ask_car_stats')],
        [InlineKeyboardButton("👤 Статистика по фамилии", callback_data='main_ask_driver_stats')],
        [InlineKeyboardButton("📥 Экспорт в Excel", callback_data='main_export_menu')],
        [InlineKeyboardButton("🏆 Топ-5", callback_data='main_top')],
        [InlineKeyboardButton("🗑️ Очистить данные", callback_data='main_clear')],
    ])

def get_export_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Полный отчет", callback_data='export_full')],
        [InlineKeyboardButton("🚗 По гос. номеру", callback_data='export_ask_car')],
        [InlineKeyboardButton("👤 По фамилии", callback_data='export_ask_driver')],
        [InlineKeyboardButton("⬅️ Назад в главное меню", callback_data='back_to_main_menu')],
    ])

cancel_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data='cancel_conversation')]])
back_to_main_menu_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в главное меню", callback_data='back_to_main_menu')]])

# --- Главное меню и навигация ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет главное меню."""
    user_id = update.effective_user.id
    welcome_text = "👋 **Главное меню**\n\nВыберите действие:"
    if user_id in user_data and not user_data[user_id].empty:
        welcome_text += f"\n\nℹ️ Загружено записей: {len(user_data[user_id])}."
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
    return ConversationHandler.END # Завершаем любой предыдущий диалог

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает пользователя в главное меню."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    welcome_text = "👋 **Главное меню**\n\nВыберите действие:"
    if user_id in user_data and not user_data[user_id].empty:
        welcome_text += f"\n\nℹ️ Загружено записей: {len(user_data[user_id])}."
    
    await query.edit_message_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

# --- Обработчики простых кнопок главного меню ---

async def handle_main_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает кнопки, не требующие диалога."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    command = query.data.split('_')[1] # 'main_stats' -> 'stats'

    has_data = user_id in user_data and not user_data[user_id].empty

    if command == 'stats':
        if not has_data: return await query.edit_message_text("ℹ️ Данные для анализа отсутствуют.", reply_markup=back_to_main_menu_keyboard)
        df = user_data[user_id]
        message = (f"📊 *Общая статистика*\n\n"
                   f"▫️ Обработано файлов: {df['Источник'].nunique()}\n"
                   f"▫️ Всего маршрутов: {len(df)}\n"
                   f"▫️ Общий заработок: *{df['Стоимость'].sum():,.2f} руб.*\n"
                   f"▫️ Уникальных машин: {df['Гос_номер'].nunique()}\n"
                   f"▫️ Уникальных водителей: {df['Водитель'].nunique()}")
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=back_to_main_menu_keyboard)

    elif command == 'top':
        if not has_data: return await query.edit_message_text("ℹ️ Данные для анализа отсутствуют.", reply_markup=back_to_main_menu_keyboard)
        df = user_data[user_id]
        top_drivers = df.groupby('Водитель')['Стоимость'].sum().nlargest(5)
        top_drivers_text = "".join([f"{i}. {d} - {t:,.0f} руб.\n" for i, (d, t) in enumerate(top_drivers.items(), 1)])
        top_cars = df.groupby('Гос_номер')['Стоимость'].sum().nlargest(5)
        top_cars_text = "".join([f"{i}. Номер {c} - {t:,.0f} руб.\n" for i, (c, t) in enumerate(top_cars.items(), 1)])
        message = (f"🏆 *Топ-5 по заработку*\n\n"
                   f"👤 *Лучшие водители:*\n{top_drivers_text or 'Нет данных'}\n"
                   f"🚗 *Самые прибыльные машины:*\n{top_cars_text or 'Нет данных'}")
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=back_to_main_menu_keyboard)

    elif command == 'clear':
        if has_data:
            del user_data[user_id]
            await query.edit_message_text("🗑️ Все загруженные данные удалены.", reply_markup=back_to_main_menu_keyboard)
        else:
            await query.edit_message_text("ℹ️ У вас нет данных для очистки.", reply_markup=back_to_main_menu_keyboard)
            
    elif command == 'export_menu':
        await query.edit_message_text("📥 **Экспорт в Excel**\n\nВыберите тип отчета:", reply_markup=get_export_menu_keyboard(), parse_mode='Markdown')

# --- Логика диалогов (ConversationHandler) ---

# Шаг 1: Функции, которые "спрашивают" у пользователя данные
async def ask_for_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data.split('_', 1)[1] # 'main_ask_car_stats' -> 'ask_car_stats'
    
    if action == 'ask_car_stats':
        await query.edit_message_text("🔢 Пожалуйста, введите 3 цифры гос. номера:", reply_markup=cancel_keyboard)
        return ASK_CAR_STATS
    elif action == 'ask_driver_stats':
        await query.edit_message_text("👤 Пожалуйста, введите фамилию водителя:", reply_markup=cancel_keyboard)
        return ASK_DRIVER_STATS
    elif action == 'ask_car': # for export
        await query.edit_message_text("🔢 Введите гос. номер для экспорта отчета:", reply_markup=cancel_keyboard)
        return ASK_CAR_EXPORT
    elif action == 'ask_driver': # for export
        await query.edit_message_text("👤 Введите фамилию для экспорта отчета:", reply_markup=cancel_keyboard)
        return ASK_DRIVER_EXPORT

# Шаг 2: Функции, которые "обрабатывают" ответ пользователя
async def handle_car_stats_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = update.effective_user.id
    df = user_data.get(user_id)
    
    if df is None or df.empty:
        await update.message.reply_text("ℹ️ Данные для анализа отсутствуют.", reply_markup=back_to_main_menu_keyboard)
        return ConversationHandler.END

    car_df = df[df['Гос_номер'].astype(str).str.contains(user_input, case=False, na=False)]
    if car_df.empty:
        await update.message.reply_text(f"❌ Машина с номером '{user_input}' не найдена.", reply_markup=back_to_main_menu_keyboard)
        return ConversationHandler.END
        
    total_trips = len(car_df)
    total_earnings = car_df['Стоимость'].sum()
    drivers = ", ".join(car_df['Водитель'].unique())
    message = (f"🚗 *Статистика по машине {user_input}*\n\n"
               f"▫️ Совершено маршрутов: {total_trips}\n"
               f"▫️ Общий заработок: *{total_earnings:,.2f} руб.*\n"
               f"▫️ Водители: {drivers}")
    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=back_to_main_menu_keyboard)
    return ConversationHandler.END

async def handle_driver_stats_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = update.effective_user.id
    df = user_data.get(user_id)
    
    if df is None or df.empty:
        await update.message.reply_text("ℹ️ Данные для анализа отсутствуют.", reply_markup=back_to_main_menu_keyboard)
        return ConversationHandler.END

    driver_df = df[df['Водитель'].str.contains(user_input, case=False, na=False)]
    if driver_df.empty:
        await update.message.reply_text(f"❌ Водитель '{user_input}' не найден.", reply_markup=back_to_main_menu_keyboard)
        return ConversationHandler.END
        
    total_trips = len(driver_df)
    total_earnings = driver_df['Стоимость'].sum()
    cars = ", ".join(driver_df['Гос_номер'].unique())
    message = (f"👤 *Статистика по водителю {user_input}*\n\n"
               f"▫️ Совершено маршрутов: {total_trips}\n"
               f"▫️ Общий заработок: *{total_earnings:,.2f} руб.*\n"
               f"▫️ Машины: {cars}")
    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=back_to_main_menu_keyboard)
    return ConversationHandler.END

# --- Логика Экспорта ---

async def handle_export_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    command = query.data.split('_')[1] # 'export_full' -> 'full'
    
    df = user_data.get(user_id)
    if df is None or df.empty:
        return await query.edit_message_text("ℹ️ Нет данных для экспорта.", reply_markup=back_to_main_menu_keyboard)
        
    if command == 'full':
        await send_excel_report(df, query.message.chat_id, context, "полный_отчет.xlsx")

async def handle_car_export_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = update.effective_user.id
    df = user_data.get(user_id)
    if df is None or df.empty:
        await update.message.reply_text("ℹ️ Данные для анализа отсутствуют.", reply_markup=back_to_main_menu_keyboard)
        return ConversationHandler.END
        
    car_df = df[df['Гос_номер'].astype(str).str.contains(user_input, case=False, na=False)]
    if car_df.empty:
        await update.message.reply_text(f"❌ Машина '{user_input}' не найдена. Экспорт отменен.", reply_markup=back_to_main_menu_keyboard)
        return ConversationHandler.END

    await send_excel_report(car_df, update.message.chat_id, context, f"отчет_машина_{user_input}.xlsx")
    return ConversationHandler.END

async def handle_driver_export_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = update.effective_user.id
    df = user_data.get(user_id)
    if df is None or df.empty:
        await update.message.reply_text("ℹ️ Данные для анализа отсутствуют.", reply_markup=back_to_main_menu_keyboard)
        return ConversationHandler.END

    driver_df = df[df['Водитель'].str.contains(user_input, case=False, na=False)]
    if driver_df.empty:
        await update.message.reply_text(f"❌ Водитель '{user_input}' не найден. Экспорт отменен.", reply_markup=back_to_main_menu_keyboard)
        return ConversationHandler.END

    await send_excel_report(driver_df, update.message.chat_id, context, f"отчет_водитель_{user_input}.xlsx")
    return ConversationHandler.END

async def send_excel_report(df: pd.DataFrame, chat_id: int, context: ContextTypes.DEFAULT_TYPE, filename: str):
    """Вспомогательная функция для создания и отправки Excel файла."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Отчет')
        worksheet = writer.sheets['Отчет']
        for idx, col in enumerate(df):
            max_len = max(df[col].astype(str).map(len).max(), len(str(df[col].name))) + 1
            worksheet.set_column(idx, idx, max_len)
    output.seek(0)
    await context.bot.send_document(chat_id=chat_id, document=output, filename=filename,
                                    caption='📊 Ваш отчет готов.')

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущий диалог и возвращает в главное меню."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    welcome_text = "👋 **Главное меню**\n\nДействие отменено. Выберите новое:"
    if user_id in user_data and not user_data[user_id].empty:
        welcome_text += f"\n\nℹ️ Загружено записей: {len(user_data[user_id])}."
    
    await query.edit_message_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
    return ConversationHandler.END

# --- Прочие обработчики ---

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file = await update.message.document.get_file()
    file_name = update.message.document.file_name
    if not file_name.lower().endswith('.xlsx'):
        await update.message.reply_text("❌ Пожалуйста, отправьте файл в формате .xlsx")
        return
    await update.message.reply_text(f"⏳ Получил файл '{file_name}'. Обрабатываю...")
    file_content = await file.download_as_bytearray()
    new_df = process_excel_file(bytes(file_content), file_name)
    if new_df is None or new_df.empty:
        await update.message.reply_text(f"⚠️ Не удалось извлечь данные из файла '{file_name}'.")
        return
    if user_id in user_data:
        user_data[user_id] = pd.concat([user_data[user_id], new_df], ignore_index=True)
    else:
        user_data[user_id] = new_df
    
    message_text = (f"✅ Файл '{file_name}' успешно обработан!\n"
                    f"Добавлено записей: {len(new_df)}\n"
                    f"Всего загружено: {len(user_data[user_id])}\n\n"
                    "Что вы хотите сделать дальше?")
    await update.message.reply_text(message_text, reply_markup=post_upload_keyboard)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive")
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
    def log_message(self, format, *args):
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    httpd.serve_forever()

if __name__ == '__main__':
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TOKEN: raise ValueError("Необходимо установить переменную окружения TELEGRAM_TOKEN")
    application = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_for_input, pattern='^main_ask_car_stats$'),
            CallbackQueryHandler(ask_for_input, pattern='^main_ask_driver_stats$'),
            CallbackQueryHandler(ask_for_input, pattern='^export_ask_car$'),
            CallbackQueryHandler(ask_for_input, pattern='^export_ask_driver$'),
        ],
        states={
            ASK_CAR_STATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_car_stats_input)],
            ASK_DRIVER_STATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_driver_stats_input)],
            ASK_CAR_EXPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_car_export_input)],
            ASK_DRIVER_EXPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_driver_export_input)],
        },
        fallbacks=[
            CommandHandler('start', start),
            CallbackQueryHandler(cancel_conversation, pattern='^cancel_conversation$')
        ],
        per_user=True,
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    
    application.add_handler(CallbackQueryHandler(handle_main_menu_buttons, pattern='^main_'))
    application.add_handler(CallbackQueryHandler(handle_export_buttons, pattern='^export_full$'))
    application.add_handler(CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'))
    
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    threading.Thread(target=run_health_check_server, daemon=True).start()
    
    print("Бот запущен в финальной профессиональной версии (v3.0)...")
    application.run_polling()

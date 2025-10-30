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
    CallbackQueryHandler
)
# Импортируем класс ошибки, чтобы ее ловить
from telegram.error import BadRequest
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from parser import process_excel_file

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

user_data = {}

# --- Клавиатуры для удобства ---
back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_menu')]])

# НОВИНКА: Клавиатура после загрузки файла
post_upload_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 Отчет по авто", callback_data='summary_car')],
    [InlineKeyboardButton("👤 Отчет по водителям", callback_data='summary_driver')],
    [InlineKeyboardButton("⬅️ В главное меню", callback_data='back_to_menu')]
])

def get_main_menu(user_id):
    welcome_text = (
        "👋 **Главное меню**\n\n"
        "Отправьте мне Excel-файл для анализа или используйте кнопки ниже для просмотра статистики."
    )
    if user_id in user_data and not user_data[user_id].empty:
        welcome_text += f"\n\nℹ️ Загружено записей: {len(user_data[user_id])}."
    
    keyboard = [
        [InlineKeyboardButton("📊 Общая статистика", callback_data='stats')],
        [InlineKeyboardButton("🏆 Топ-5", callback_data='top'), InlineKeyboardButton("📥 Экспорт в Excel", callback_data='export')],
        [InlineKeyboardButton("🗑️ Очистить данные", callback_data='clear')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return welcome_text, reply_markup

# --- ОБРАБОТЧИКИ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, markup = get_main_menu(user_id)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    command = query.data

    try:
        if command == 'back_to_menu':
            text, markup = get_main_menu(user_id)
            await query.edit_message_text(text, reply_markup=markup, parse_mode='Markdown')
            return

        has_data = user_id in user_data and not user_data[user_id].empty

        # --- НОВИНКА: Обработка кнопок сводки ---
        if command == 'summary_car' or command == 'summary_driver':
            if not has_data:
                await query.edit_message_text("ℹ️ Данные для анализа отсутствуют.", reply_markup=back_keyboard)
                return
            
            df = user_data[user_id]
            group_by_col = 'Гос_номер' if command == 'summary_car' else 'Водитель'
            title = "🚗 Сводка по автомобилям" if command == 'summary_car' else "👤 Сводка по водителям"
            
            summary = df.groupby(group_by_col)['Стоимость'].sum().sort_values(ascending=False)
            
            summary_text = f"**{title}**\n\n"
            if summary.empty:
                summary_text += "Нет данных для отображения."
            else:
                for item, total in summary.items():
                    summary_text += f"▫️ {item}: *{total:,.0f} руб.*\n"
            
            await query.edit_message_text(summary_text, parse_mode='Markdown', reply_markup=back_keyboard)
        
        # ... (остальные кнопки без изменений) ...
        elif command == 'stats':
            # ...
        
        elif command == 'export':
             # ...
             
    except BadRequest as e:
        # ИСПРАВЛЕНИЕ: Ловим ошибку "Message is not modified" и просто игнорируем ее
        if "Message is not modified" in str(e):
            logging.info("Ignoring 'Message is not modified' error.")
        else:
            logging.error(f"An unexpected BadRequest error occurred: {e}")
    except Exception as e:
        logging.error(f"An error occurred in button_callback: {e}")
        await query.edit_message_text("❌ Произошла ошибка при обработке вашего запроса.", reply_markup=back_keyboard)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # ... (логика обработки файла)
    file = await update.message.document.get_file()
    # ...
    new_df = process_excel_file(bytes(file_content), file_name)
    # ...
    
    # НОВИНКА: Отправляем сообщение с новыми кнопками
    message_text = (
        f"✅ Файл '{file_name}' успешно обработан!\n"
        f"Добавлено записей: {len(new_df)}\n"
        f"Всего загружено: {len(user_data[user_id])}\n\n"
        "Что вы хотите сделать дальше?"
    )
    await update.message.reply_text(message_text, reply_markup=post_upload_keyboard)

# ... Остальные функции (car_stats, driver_stats, handle_document и веб-сервер) остаются без изменений ...
async def car_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data or user_data[user_id].empty:
        await update.message.reply_text("ℹ️ Данные для анализа отсутствуют. Загрузите файлы.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ **Ошибка:** Вы не указали номер.\nПример: `/car 123`", parse_mode='Markdown')
        return
    car_number = context.args[0]
    df = user_data[user_id]
    car_df = df[df['Гос_номер'].astype(str).str.contains(car_number, case=False, na=False)]
    if car_df.empty:
        await update.message.reply_text(f"❌ Машина с госномером '{car_number}' не найдена.")
        return
    total_trips = len(car_df)
    total_earnings = car_df['Стоимость'].sum()
    drivers = ", ".join(car_df['Водитель'].unique())
    message = (f"🚗 *Статистика по машине {car_number}*\n\n▫️ Совершено маршрутов: {total_trips}\n▫️ Общий заработок: *{total_earnings:,.2f} руб.*\n▫️ Водители на этой машине: {drivers}")
    await update.message.reply_text(message, parse_mode='Markdown')

async def driver_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data or user_data[user_id].empty:
        await update.message.reply_text("ℹ️ Данные для анализа отсутствуют. Загрузите файлы.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ **Ошибка:** Вы не указали фамилию.\nПример: `/driver Иванов`", parse_mode='Markdown')
        return
    driver_name = context.args[0]
    df = user_data[user_id]
    driver_df = df[df['Водитель'].str.contains(driver_name, case=False, na=False)]
    if driver_df.empty:
        await update.message.reply_text(f"❌ Водитель с фамилией '{driver_name}' не найден.")
        return
    total_trips = len(driver_df)
    total_earnings = driver_df['Стоимость'].sum()
    cars = ", ".join(driver_df['Гос_номер'].unique())
    message = (f"👤 *Статистика по водителю {driver_name}*\n\n▫️ Совершено маршрутов: {total_trips}\n▫️ Общий заработок: *{total_earnings:,.2f} руб.*\n▫️ Работал(а) на машинах: {cars}")
    await update.message.reply_text(message, parse_mode='Markdown')

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
    if user_id in user_data: user_data[user_id] = pd.concat([user_data[user_id], new_df], ignore_index=True)
    else: user_data[user_id] = new_df
    await update.message.reply_text(f"✅ Файл '{file_name}' обработан!\nДобавлено записей: {len(new_df)}\nВсего загружено: {len(user_data[user_id])}")

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.send_header("Content-type", "text/plain"); self.end_headers(); self.wfile.write(b"Bot is alive")
def run_health_check_server():
    port = int(os.environ.get("PORT", 8080)); httpd = HTTPServer(('', port), HealthCheckHandler); httpd.serve_forever()

if __name__ == '__main__':
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TOKEN: raise ValueError("Необходимо установить переменную окружения TELEGRAM_TOKEN")
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('car', car_stats))
    application.add_handler(CommandHandler('driver', driver_stats))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    threading.Thread(target=run_health_check_server, daemon=True).start()
    print("Бот запущен в финальном рабочем режиме...")
    application.run_polling()

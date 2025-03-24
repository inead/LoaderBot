import logging
import gspread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import F
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, time, timedelta
import pytz
import asyncio

# Настройки
TELEGRAM_TOKEN = "ТОКЕН_БОТА"
USERS_SHEET_NAME = "ТАБЛИЦА_БАЗЫДАННЫХ"
SHIFTS_SHEET_NAME = "ТАБЛИЦА_РАБОЧИХ_ВЫШЕШИХ_НА_СМЕНУ"

# Логирование
logging.basicConfig(level=logging.INFO)

# Подключение к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("ПУТЬ/ДО/ФАЙЛА/credentials.json", scope)
client = gspread.authorize(creds)
users_sheet = client.open(USERS_SHEET_NAME).sheet1
shifts_sheet = client.open(SHIFTS_SHEET_NAME).sheet1

# Часовой пояс (МСК)
MSK_TZ = pytz.timezone("Europe/Moscow")

# Клавиатуры
start_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[[types.KeyboardButton(text="🚀 Запустить бота")]],
    resize_keyboard=True
)
register_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[[types.KeyboardButton(text="Ознакомиться с регламентом")]],
    resize_keyboard=True
)
agree_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[[types.KeyboardButton(text="✅ Я ознакомлен и согласен")]],
    resize_keyboard=True
)
main_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[[types.KeyboardButton(text="Начать смену")]],
    resize_keyboard=True,
)
shift_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[[types.KeyboardButton(text="Закончить смену")]],
    resize_keyboard=True,
)

# Регламент
REGULATIONS = """
Регламент:...
"""


# Состояния
class Registration(StatesGroup):
    awaiting_agreement = State()
    full_name = State()
    requisites = State()
    bank = State()
    recipient = State()


# Проверка регистрации
def is_registered(user_id):
    try:
        records = users_sheet.get_all_values()
        return any(row[0] == str(user_id) for row in records)
    except Exception as e:
        logging.error(f"Ошибка проверки регистрации: {e}")
        return False


# Проверка активной смены
def has_active_shift(full_name):
    records = shifts_sheet.get_all_values()
    return any(row[2] == full_name and not row[7] for row in records)


# Проверка, может ли пользователь начать смену
def can_start_shift(full_name):
    try:
        records = shifts_sheet.get_all_values()
        today_date = datetime.now(MSK_TZ).strftime("%Y-%m-%d")
        now_time = datetime.now(MSK_TZ).time()  # Время с учетом часового пояса

        logging.info(f"Проверка смены для {full_name} на дату {today_date} в {now_time}")

        # Проверяем, есть ли уже смена для данного пользователя сегодня
        for row in records:
            if row[2] == full_name and row[1] == today_date and not row[7]:
                logging.info(f"Найдена активная смена для {full_name} сегодня.")
                return False  # Смена уже была начата сегодня

        # Закомментированная проверка на 6 утра
        # if now_time < time(6, 0):
        #     logging.info(f"Текущее время {now_time} меньше 6:00. Смена не может быть начата.")
        #     return False  # Смена может быть начата только после 6:00

        logging.info(f"Смена может быть начата для {full_name}.")
        return True  # Смена ещё не была начата

    except Exception as e:
        logging.error(f"Ошибка в функции can_start_shift: {e}")
        return False


# Функция для вычисления и записи отработанных часов
def calculate_and_update_worked_hours():
    try:
        records = shifts_sheet.get_all_values()

        for i, row in enumerate(records):
            if row[7]:  # Проверяем, что смена завершена (есть время окончания)
                start_time = datetime.strptime(row[6], "%H:%M:%S").time()  # Время начала смены
                end_time = datetime.strptime(row[7], "%H:%M:%S").time()  # Время окончания смены

                # Преобразуем время в datetime для удобства вычислений
                start_datetime = datetime.combine(datetime.today(), start_time)
                end_datetime = datetime.combine(datetime.today(), end_time)

                # Вычисляем разницу между временем окончания и начала
                shift_duration = end_datetime - start_datetime

                # Преобразуем разницу в часы и минуты
                total_seconds = int(shift_duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60

                # Форматируем результат в строку "часы:минуты"
                worked_hours = f"{hours}:{minutes:02d}"

                # Обновляем столбец "I" (девятый столбец) для текущей строки
                shifts_sheet.update_cell(i + 1, 9, worked_hours)

        logging.info("Отработанные часы успешно обновлены в таблице.")
    except Exception as e:
        logging.error(f"Ошибка при вычислении и обновлении отработанных часов: {e}")


# Добавление записи в таблицу Bot-test
def add_shift_to_bot_test(full_name, start_time, end_time, requisites, bank, recipient):
    try:
        next_row = len(shifts_sheet.get_all_values()) + 1
        now_date = datetime.now(MSK_TZ).strftime("%Y-%m-%d")

        # Добавляем новую строку с данными
        shifts_sheet.append_row([
            next_row,  # Номер строки (A)
            now_date,  # Дата (B)
            full_name,  # ФИО (C)
            "",  # Пустой столбец (D)
            "",  # Пустой столбец (E)
            "",  # Пустой столбец (F)
            start_time,  # Время начала смены (G)
            end_time,  # Время окончания смены (H)
            "",  # Отработанные часы (I) — будут обновлены позже
            "",  # Пустой столбец (J)
            "",  # Пустой столбец (K)
            "",  # Пустой столбец (L)
            "",  # Пустой столбец (M)
            requisites,  # Реквизиты (N)
            bank,  # Банк (O)
            recipient  # Получатель (P)
        ])
    except Exception as e:
        logging.error(f"Ошибка добавления записи в таблицу Bot-test: {e}")


# Добавление пользователя в таблицу PersonData
def add_user_to_person_data(user_id, full_name, requisites, bank, recipient):
    try:
        users_sheet.append_row([str(user_id), full_name, requisites, bank, recipient])
    except Exception as e:
        logging.error(f"Ошибка добавления пользователя: {e}")


# Бот и диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Привет! Запустите бота, нажав кнопку ниже.", reply_markup=start_keyboard)


@dp.message(F.text == "🚀 Запустить бота")
async def handle_start_button(message: types.Message):
    user_id = message.from_user.id
    if is_registered(user_id):
        await message.answer("Вы зарегистрированы. Нажмите кнопку ниже, чтобы начать смену", reply_markup=main_keyboard)
    else:
        await message.answer("Для начала регистрации, ознакомьтесь с регламентом", reply_markup=register_keyboard)


@dp.message(F.text == "Ознакомиться с регламентом")
async def show_regulations(message: types.Message, state: FSMContext):
    await state.set_state(Registration.awaiting_agreement)  # Установим состояние ожидания согласия
    await message.answer(
        REGULATIONS,  # Текст регламента
        reply_markup=agree_keyboard  # Кнопка для подтверждения
    )


@dp.message(F.text == "✅ Я ознакомлен и согласен", Registration.awaiting_agreement)
async def agree_regulations(message: types.Message, state: FSMContext):
    await state.set_state(Registration.full_name)
    # Преобразуем клавиатуру, чтобы она не отображалась после этого шага
    await message.answer("Введите ваше ФИО:", reply_markup=types.ReplyKeyboardRemove())


@dp.message(Registration.full_name)
async def register_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    if not full_name:
        await message.answer("⚠️ ФИО не может быть пустым. Пожалуйста, введите ваше ФИО.")
        return
    await state.update_data(full_name=full_name)
    await state.set_state(Registration.requisites)
    await message.answer("Введите реквизиты банка:")


@dp.message(Registration.requisites)
async def register_requisites(message: types.Message, state: FSMContext):
    requisites = message.text.strip()
    if not requisites:
        await message.answer("⚠️ Реквизиты не могут быть пустыми. Пожалуйста, введите реквизиты.")
        return
    await state.update_data(requisites=requisites)
    await state.set_state(Registration.bank)
    await message.answer("Введите название банка:")


@dp.message(Registration.bank)
async def register_bank(message: types.Message, state: FSMContext):
    bank = message.text.strip()
    if not bank:
        await message.answer("⚠️ Название банка не может быть пустым. Пожалуйста, введите название банка.")
        return
    await state.update_data(bank=bank)
    await state.set_state(Registration.recipient)
    await message.answer("Введите ФИО получателя:")


@dp.message(Registration.recipient)
async def register_recipient(message: types.Message, state: FSMContext):
    recipient = message.text.strip()
    if not recipient:
        await message.answer("⚠️ ФИО получателя не может быть пустым. Пожалуйста, введите ФИО получателя.")
        return

    user_data = await state.get_data()
    user_id = message.from_user.id
    # Добавление пользователя в таблицу PersonData
    add_user_to_person_data(user_id, user_data["full_name"], user_data["requisites"], user_data["bank"], recipient)

    await state.clear()
    # Убираем клавиатуру после завершения регистрации
    await message.answer("✅ Регистрация завершена!", reply_markup=types.ReplyKeyboardRemove())
    # Показать клавиатуру для начала смены
    await message.answer("Нажмите кнопку ниже для начала смены.", reply_markup=main_keyboard)


@dp.message(F.text == "Начать смену")
async def start_shift(message: types.Message):
    user_id = message.from_user.id
    row_number = users_sheet.find(str(user_id)).row
    user_data = users_sheet.row_values(row_number)
    full_name = user_data[1]
    now = datetime.now(MSK_TZ).strftime("%H:%M:%S")
    today_date = datetime.now(MSK_TZ).strftime("%Y-%m-%d")

    # Проверка, может ли пользователь начать смену
    if not can_start_shift(full_name):
        await message.answer(
            "❌ Вы не можете начать смену. У вас уже есть активная смена.",
            reply_markup=main_keyboard
        )
        return

    # Если можно начать смену, добавляем её в таблицу
    try:
        add_shift_to_bot_test(
            full_name=full_name,
            start_time=now,
            end_time="",  # Время окончания смены пока пустое
            requisites=user_data[2],  # Реквизиты из таблицы PersonData
            bank=user_data[3],  # Банк из таблицы PersonData
            recipient=user_data[4]  # Получатель из таблицы PersonData
        )
        await message.answer("🕒 Смена начата", reply_markup=shift_keyboard)
    except Exception as e:
        logging.error(f"Ошибка при добавлении смены: {e}")
        await message.answer("⚠️ Произошла ошибка при начале смены. Попробуйте позже.")


@dp.message(F.text == "Закончить смену")
async def end_shift(message: types.Message):
    user_id = message.from_user.id
    row_number = users_sheet.find(str(user_id)).row
    user_data = users_sheet.row_values(row_number)
    now = datetime.now(MSK_TZ).strftime("%H:%M:%S")

    records = shifts_sheet.get_all_values()
    for i in range(len(records) - 1, 0, -1):
        if records[i][2] == user_data[1] and not records[i][7]:  # Находим активную смену
            # Обновляем время окончания смены (столбец H)
            shifts_sheet.update_cell(i + 1, 8, now)

            # Вычисляем и обновляем отработанные часы (столбец I)
            calculate_and_update_worked_hours()

            await message.answer("✅ Смена завершена", reply_markup=main_keyboard)
            return
    await message.answer("⚠️ У вас нет активных смен.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

"""Прохождение теста «Фактологичность»."""

import logging
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _
from aiogram.utils.i18n import lazy_gettext as __
from sqlalchemy.ext.asyncio import AsyncSession

from common.keyboard import get_callback_btns
from database.orm_answers import CORRECT_ANSWERS as correct_answers
from database.orm_answers import (
    orm_get_current_question,
    orm_get_progress,
    orm_get_result_statistics,
    orm_save_answer,
)
from handlers.start import main_screen

logger = logging.getLogger(__name__)

# Инициализируем роутер уровня модуля
factuality_router = Router()

# Определяем состояния
class TestStates(StatesGroup):
    QUESTION_START = State()
    QUESTION_PROCESS = State()

# Константы для вопросов
QUESTION_1 = __("Вопрос 1:\n\nСколько девочек сегодня оканчивают начальную школу в странах с низким уровнем доходов?")
QUESTION_2 = __("Вопрос 2:\n\nГде живет большая часть населения мира?")
QUESTION_3 = __("Вопрос 3:\n\nЗа последние 20 лет доля мирового населения, живущего в нищете...")
QUESTION_4 = __("Вопрос 4:\n\nКакова сегодня ожидаемая продолжительность жизни в мире?")
QUESTION_5 = __("Вопрос 5:\n\nСегодня в мире насчитывается 2 миллиарда детей в возрасте от 0 до 15 лет. Сколько детей, согласно прогнозу ООН, будет в мире в 2100 году?")
QUESTION_6 = __("Вопрос 6:\n\nПо прогнозам ООН, к 2100 году население земного шара увеличится на 4 миллиарда человек. За счет чего это произойдет?")
QUESTION_7 = __("Вопрос 7:\n\nКак за последние 100 лет изменилось количество смертей в год, вызванных стихийными бедствиями?")
QUESTION_8 = __("Вопрос 8:\n\nСегодня население земного шара составляет около 7 миллиардов человек. Какая карта лучше всего показывает их распределение?\n\n<i>(Карта которая в описании бота ⬆️.\nКаждая фигурка обозначает 1 миллиард человек)</i>")
QUESTION_9 = __("Вопрос 9:\n\nСколько годовалых детей в мире прививается сегодня от каких-либо болезней?")
QUESTION_10 = __("Вопрос 10:\n\nВ среднем по миру к 30 годам мужчины тратят на учебу 10 лет своей жизни. Сколько лет тратят на учебу к тому же возрасту женщины?")
QUESTION_11 = __("Вопрос 11:\n\nВ 1996 году тигры, гигантские панды и черные носороги вошли в список вымирающих видов. Сколько из этих трех видов сегодня находятся под угрозой исчезновения?")
QUESTION_12 = __("Вопрос 12:\n\nСколько человек в мире имеют доступ к электричеству?")
QUESTION_13 = __("Вопрос 13:\n\nЭксперты по глобальному климату считают, что в течение следующих 100 лет средняя температура...")

# Константы для ответов
ANSWER_1_1 = __('1) 20 процентов')
ANSWER_1_2 = __('2) 40 процентов')
ANSWER_1_3 = __('3) 60 процентов')

ANSWER_2_1 = __('1) В странах с низким уровнем доходов')
ANSWER_2_2 = __('2) В странах со средним уровнем доходов')
ANSWER_2_3 = __('3) В странах с высоким уровнем доходов')

ANSWER_3_1 = __('1) ...почти удвоилась')
ANSWER_3_2 = __('2) ...осталась почти неизменной')
ANSWER_3_3 = __('3) ...сократилась почти вдвое')

ANSWER_4_1 = __('1) 50 лет')
ANSWER_4_2 = __('2) 60 лет')
ANSWER_4_3 = __('3) 70 лет')

ANSWER_5_1 = __('1) 4 миллиарда')
ANSWER_5_2 = __('2) 3 миллиарда')
ANSWER_5_3 = __('3) 2 миллиарда')

ANSWER_6_1 = __('1) Будет больше детей (до 15 лет)')
ANSWER_6_2 = __('2) Будет больше взрослых (от 15 до 74 лет)')
ANSWER_6_3 = __('3) Будет больше стариков (от 75 лет)')

ANSWER_7_1 = __('1) Увеличилось более чем в два раза')
ANSWER_7_2 = __('2) Осталось почти неизменным')
ANSWER_7_3 = __('3) Уменьшилось более чем в два раза')

ANSWER_8_1 = __('1) Карта I')
ANSWER_8_2 = __('2) Карта II')
ANSWER_8_3 = __('3) Карта III')

ANSWER_9_1 = __('1) 20 процентов')
ANSWER_9_2 = __('2) 50 процентов')
ANSWER_9_3 = __('3) 80 процентов')

ANSWER_10_1 = __('1) 9 лет')
ANSWER_10_2 = __('2) 6 лет')
ANSWER_10_3 = __('3) 3 года')

ANSWER_11_1 = __('1) Два')
ANSWER_11_2 = __('2) Один')
ANSWER_11_3 = __('3) Ни одного')

ANSWER_12_1 = __('1) 20 процентов')
ANSWER_12_2 = __('2) 50 процентов')
ANSWER_12_3 = __('3) 80 процентов')

ANSWER_13_1 = __('1) ...повысится')
ANSWER_13_2 = __('2) ...останется неизменной')
ANSWER_13_3 = __('3) ...понизится')

# Обновленный словарь
questions_answers = {
    1: (QUESTION_1, {'question1_1': ANSWER_1_1, 'question1_2': ANSWER_1_2, 'question1_3': ANSWER_1_3}),
    2: (QUESTION_2, {'question2_1': ANSWER_2_1, 'question2_2': ANSWER_2_2, 'question2_3': ANSWER_2_3}),
    3: (QUESTION_3, {'question3_1': ANSWER_3_1, 'question3_2': ANSWER_3_2, 'question3_3': ANSWER_3_3}),
    4: (QUESTION_4, {'question4_1': ANSWER_4_1, 'question4_2': ANSWER_4_2, 'question4_3': ANSWER_4_3}),
    5: (QUESTION_5, {'question5_1': ANSWER_5_1, 'question5_2': ANSWER_5_2, 'question5_3': ANSWER_5_3}),
    6: (QUESTION_6, {'question6_1': ANSWER_6_1, 'question6_2': ANSWER_6_2, 'question6_3': ANSWER_6_3}),
    7: (QUESTION_7, {'question7_1': ANSWER_7_1, 'question7_2': ANSWER_7_2, 'question7_3': ANSWER_7_3}),
    8: (QUESTION_8, {'question8_1': ANSWER_8_1, 'question8_2': ANSWER_8_2, 'question8_3': ANSWER_8_3}),
    9: (QUESTION_9, {'question9_1': ANSWER_9_1, 'question9_2': ANSWER_9_2, 'question9_3': ANSWER_9_3}),
    10: (QUESTION_10, {'question10_1': ANSWER_10_1, 'question10_2': ANSWER_10_2, 'question10_3': ANSWER_10_3}),
    11: (QUESTION_11, {'question11_1': ANSWER_11_1, 'question11_2': ANSWER_11_2, 'question11_3': ANSWER_11_3}),
    12: (QUESTION_12, {'question12_1': ANSWER_12_1, 'question12_2': ANSWER_12_2, 'question12_3': ANSWER_12_3}),
    13: (QUESTION_13, {'question13_1': ANSWER_13_1, 'question13_2': ANSWER_13_2, 'question13_3': ANSWER_13_3})
}

# # Словарь вопросов-ответов
# questions_answers = {
#     1: (__("Вопрос 1:\n\nСколько девочек сегодня оканчивают начальную школу в странах с низким уровнем доходов?"),
#         {'question1_1': __('1) 20 процентов'),
#          'question1_2': __('2) 40 процентов'),
#          'question1_3': __('3) 60 процентов')}),
#     2: (__("Вопрос 2:\n\nГде живет большая часть населения мира?"),
#         {'question2_1': __('1) В странах с низким уровнем доходов'),
#          'question2_2': __('2) В странах со средним уровнем доходов'),
#          'question2_3': __('3) В странах с высоким уровнем доходов')}),
#     3: (__("Вопрос 3:\n\nЗа последние 20 лет доля мирового населения, живущего в нищете..."),
#         {'question3_1': __('1) ...почти удвоилась'),
#          'question3_2': __('2) ...осталась почти неизменной'),
#          'question3_3': __('3) ...сократилась почти вдвое')}),
#     4: (__("Вопрос 4:\n\nКакова сегодня ожидаемая продолжительность жизни в мире?"),
#         {'question4_1': __('1) 50 лет'),
#          'question4_2': __('2) 60 лет'),
#          'question4_3': __('3) 70 лет')}),
#     5: (__("Вопрос 5:\n\nСегодня в мире насчитывается 2 миллиарда детей в возрасте от 0 до 15 лет. Сколько детей, согласно прогнозу ООН, будет в мире в 2100 году?"),
#         {'question5_1': __('1) 4 миллиарда'),
#          'question5_2': __('2) 3 миллиарда'),
#          'question5_3': __('3) 2 миллиарда')}),
#     6: (__("Вопрос 6:\n\nПо прогнозам ООН, к 2100 году население земного шара увеличится на 4 миллиарда человек. За счет чего это произойдет?"),
#         {'question6_1': __('1) Будет больше детей (до 15 лет)'),
#          'question6_2': __('2) Будет больше взрослых (от 15 до 74 лет)'),
#          'question6_3': __('3) Будет больше стариков (от 75 лет)')}),
#     7: (__("Вопрос 7:\n\nКак за последние 100 лет изменилось количество смертей в год, вызванных стихийными бедствиями?"),
#         {'question7_1': __('1) Увеличилось более чем в два раза'),
#          'question7_2': __('2) Осталось почти неизменным'),
#          'question7_3': __('3) Уменьшилось более чем в два раза')}),
#     8: (__("Вопрос 8:\n\nСегодня население земного шара составляет около 7 миллиардов человек. Какая карта лучше всего показывает их распределение?\n\n<i>(Карта которая в описании бота ⬆️.\nКаждая фигурка обозначает 1 миллиард человек)</i>"),
#         {'question8_1': __('1) Карта I'),
#          'question8_2': __('2) Карта II'),
#          'question8_3': __('3) Карта III')}),
#     9: (__("Вопрос 9:\n\nСколько годовалых детей в мире прививается сегодня от каких-либо болезней?"),
#         {'question9_1': __('1) 20 процентов'),
#          'question9_2': __('2) 50 процентов'),
#          'question9_3': __('3) 80 процентов')}),
#     10: (__("Вопрос 10:\n\nВ среднем по миру к 30 годам мужчины тратят на учебу 10 лет своей жизни. Сколько лет тратят на учебу к тому же возрасту женщины?"),
#         {'question10_1': __('1) 9 лет'),
#          'question10_2': __('2) 6 лет'),
#          'question10_3': __('3) 3 года')}),
#     11: (__("Вопрос 11:\n\nВ 1996 году тигры, гигантские панды и черные носороги вошли в список вымирающих видов. Сколько из этих трех видов сегодня находятся под угрозой исчезновения?"),
#         {'question11_1': __('1) Два'),
#          'question11_2': __('2) Один'),
#          'question11_3': __('3) Ни одного')}),
#     12: (__("Вопрос 12:\n\nСколько человек в мире имеют доступ к электричеству?"),
#         {'question12_1': __('1) 20 процентов'),
#          'question12_2': __('2) 50 процентов'),
#          'question12_3': __('3) 80 процентов')}),
#     13: (__("Вопрос 13:\n\nЭксперты по глобальному климату считают, что в течение следующих 100 лет средняя температура..."),
#         {'question13_1': __('1) ...повысится'),
#          'question13_2': __('2) ...останется неизменной'),
#          'question13_3': __('3) ...понизится')})
# }

# Обработчик инлайн-кнопки "Назад"
@factuality_router.callback_query(F.data == 'back_to_main')
async def factuality_command(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Вернуть пользователя на главный экран."""
    user_id = callback_query.from_user.id
    current_question, result = await orm_get_progress(session, user_id)
    current_question = current_question or 1
    text, reply_markup = main_screen(current_question, result)
    new_message = await callback_query.message.edit_text(
        text=text,
        reply_markup=reply_markup,
    )
    await state.set_state(None)
    await state.update_data(
        last_message_id=new_message.message_id,
        current_question=current_question,
        result=result,
    )
    await callback_query.answer()

# Обработчик инлайн-кнопки "Назад" из donate
@factuality_router.callback_query(F.data == 'donate_back_to_main')
async def donate_back_to_main(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Вернуться со счёта доната на главный экран."""
    user_id = callback_query.from_user.id
    try:
        await callback_query.message.delete()
    except TelegramAPIError:
        logger.info("Не удалось удалить счёт при возврате в меню")

    current_question, result = await orm_get_progress(session, user_id)
    current_question = current_question or 1
    text, reply_markup = main_screen(current_question, result)
    new_message = await callback_query.message.answer(
        text=text,
        reply_markup=reply_markup,
    )
    await state.set_state(None)
    await state.update_data(
        last_message_id=new_message.message_id,
        current_question=current_question,
        result=result,
    )
    await callback_query.answer()

# Обработчик нажатия на инлайн-кнопку "Начать тест", или "Продолжить тест"
@factuality_router.callback_query(F.data.in_(["start_test", "continue_test"]))
async def start_test_callback(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    workflow_data: dict,
) -> None:
    """Открыть актуальный вопрос теста."""
    user_id = callback_query.from_user.id
    current_question = await orm_get_current_question(session, user_id)
    analytics = workflow_data['analytics']

    if current_question is None or current_question > 13:
        await callback_query.answer(
            _("Тест уже завершён. Вернитесь в главное меню."),
            show_alert=True,
        )
        return

    question_text = questions_answers[current_question][0]
    question_answers = questions_answers[current_question][1]
    new_message = await callback_query.message.edit_text(
        text=str(question_text),
        reply_markup=get_callback_btns(btns={str(v): k for k, v in question_answers.items()},
                                       sizes=(1,1,1))) # type: ignore
    # Сохраняем новый message_id
    await state.update_data(
        last_message_id=new_message.message_id,
        current_question=current_question,
    )

    # Сохраняем временную метку
    timestamp = datetime.now().timestamp()
    await state.update_data(timestamp=timestamp)

    await state.set_state(TestStates.QUESTION_PROCESS)
    await callback_query.answer()

    await analytics(user_id=user_id,
                    category_name="/process",
                    command_name="/start_test")

# Обработчик для inline ответов на вопросы
@factuality_router.callback_query(StateFilter(TestStates.QUESTION_PROCESS), F.data.startswith('question'))
async def process_question(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    workflow_data: dict,
) -> None:
    """Проверить и атомарно сохранить выбранный ответ."""
    user_id = callback_query.from_user.id
    data = await state.get_data()
    analytics = workflow_data['analytics']
    match = re.fullmatch(r"question(\d+)_(\d+)", callback_query.data or "")
    if match is None:
        await callback_query.answer(_("Некорректный ответ."), show_alert=True)
        return

    last_message_id = data.get("last_message_id")
    if last_message_id and callback_query.message.message_id != last_message_id:
        await callback_query.answer(
            _("Это меню устарело. Используйте последнее сообщение бота."),
            show_alert=True,
        )
        return

    callback_question, answer = map(int, match.groups())
    if callback_question not in range(1, 14) or answer not in {1, 2, 3}:
        await callback_query.answer(_("Некорректный ответ."), show_alert=True)
        return

    current_timestamp = datetime.now().timestamp()
    started_at = data.get("timestamp", current_timestamp)
    answer_time = round(max(0.0, current_timestamp - started_at), 2)

    try:
        saved = await orm_save_answer(
            session=session,
            user_id=user_id,
            question=callback_question,
            answer=answer,
            answer_time=answer_time,
            correct_answers=correct_answers,
        )
    except Exception:
        await session.rollback()
        logger.exception("Не удалось сохранить ответ пользователя %s", user_id)
        await callback_query.answer(
            _("Ответ не сохранён. Попробуйте ещё раз."),
            show_alert=True,
        )
        return

    current_question = saved.next_question
    if current_question is None:
        await callback_query.answer(
            _("Не удалось найти данные теста. Нажмите /start."),
            show_alert=True,
        )
        return

    if not saved.accepted and current_question > 13:
        text, reply_markup = main_screen(current_question, saved.result)
        new_message = await callback_query.message.edit_text(
            text=text,
            reply_markup=reply_markup,
        )
        await state.update_data(
            last_message_id=new_message.message_id,
            current_question=current_question,
            result=saved.result,
        )
        await state.set_state(None)
        await callback_query.answer(_("Этот ответ уже был принят."))
        return

    if not saved.accepted:
        question_text, question_answers = questions_answers[current_question]
        new_message = await callback_query.message.edit_text(
            text=str(question_text),
            reply_markup=get_callback_btns(
                btns={str(value): key for key, value in question_answers.items()},
                sizes=(1, 1, 1),
            ),
        )
        await state.update_data(
            last_message_id=new_message.message_id,
            current_question=current_question,
            timestamp=current_timestamp,
        )
        await callback_query.answer(_("Показан актуальный вопрос."))
        return

    await state.update_data(
        **{
            f"answer_{callback_question}": answer,
            f"answer_{callback_question}_time": answer_time,
            "current_question": current_question,
            "timestamp": current_timestamp,
        }
    )

    if current_question <= 13:
        question_text, question_answers = questions_answers[current_question]
        new_message = await callback_query.message.edit_text(
            text=str(question_text),
            reply_markup=get_callback_btns(
                btns={str(value): key for key, value in question_answers.items()},
                sizes=(1, 1, 1),
            ),
        )
        command_name = "/process_test"
        finished = False
    else:
        text = _("Тест завершен!\n\nВаш результат: {correct_count}/13").format(
            correct_count=saved.result
        )
        new_message = await callback_query.message.edit_text(
            text=str(text),
            reply_markup=get_callback_btns(
                btns={
                    _("Правильные ответы"): "correct_answers",
                    _("О книге"): "about_book",
                    _("О тесте"): "about_test",
                },
                sizes=(1, 1, 1),
            ),
        )
        command_name = "/finish_test"
        finished = True

    await state.update_data(
        last_message_id=new_message.message_id,
        result=saved.result if finished else None,
        answer_total_time=saved.total_time if finished else None,
    )
    if finished:
        await state.set_state(None)
    await callback_query.answer()
    await analytics(
        user_id=user_id,
        category_name="/process",
        command_name=command_name,
    )

# Обработчик нажатия на инлайн-кнопку "О книге"
@factuality_router.callback_query(F.data == 'about_book')
async def about_book(
    callback_query: CallbackQuery,
    state: FSMContext,
    workflow_data: dict,
) -> None:
    """Показать информацию о книге."""
    user_id = callback_query.from_user.id

    text = _("📖 О книге «Фактологичность»\n\n"
            "Ханс Рослинг, профессор международного здравоохранения, провёл тесты среди тысяч людей по всему миру: "
            "студентов, политиков, учёных и даже нобелевских лауреатов.\n\n"
            "Большинство участников справлялись хуже, чем если бы ответы выбирала обезьяна наугад. "
            "Случайное угадывание даёт 4 из 13 правильных ответов, а люди набирали только 2-3.\n\n"
            "Почему? Рослинг выделяет 10 инстинктов, которые заставляют нас драматизировать реальность: "
            "инстинкт разрыва, негативности, прямой линии, страха и другие. Они искажают наше восприятие мира.\n\n"
            "Мир стал намного лучше, чем мы думаем, но наш мозг упорно цепляется за устаревшие представления. "
            "Книга учит мыслить фактологично — опираться на данные, а не на инстинкты.")

    new_message = await callback_query.message.edit_text(
        text=str(text),
        reply_markup=get_callback_btns(btns={_('↩️ Назад'): 'back_to_main'},
                                       sizes=(1,1))) # type: ignore
    await state.update_data(last_message_id=new_message.message_id)
    await callback_query.answer()

    analytics = workflow_data['analytics']
    await analytics(user_id=user_id,
                    category_name="/info",
                    command_name="/about_book")


# Обработчик нажатия на инлайн-кнопку "О тесте"
@factuality_router.callback_query(F.data == 'about_test')
async def about_test(
    callback_query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    workflow_data: dict,
) -> None:
    """Показать описание и агрегированную статистику теста."""
    user_id = callback_query.from_user.id

    # получаем все result юзеров
    cnt_res, avg_result = await orm_get_result_statistics(session)

    text = _("📊 О тесте\n\n"
            "Этот бот проводит оригинальный тест из книги «Фактологичность». "
            "13 вопросов о глобальных трендах: бедность, образование, продолжительность жизни, экология.\n\n"
            "Чем полезен тест?\n"
            "Он показывает разрыв между вашими представлениями и реальными данными. "
            "Вопросы составлены так, что большинство людей ошибаются — не от незнания, а из-за когнитивных искажений.\n\n"
            "Интерпретация результатов:\n"
            "• До 4 баллов — ваш мозг драматизирует реальность\n"
            "• 5-8 баллов — близко к среднему, есть над чем работать\n"
            "• 9+ баллов — фактологичное мышление, редкий результат\n\n"
            "Статистика пользователей:\n"
            "• Прошли тест:  {cnt_res}\n"
            "• Средний балл: {avg_result:.1f}").format(cnt_res=cnt_res, avg_result=avg_result)

    new_message = await callback_query.message.edit_text(
        text=str(text),
        reply_markup=get_callback_btns(btns={_('↩️ Назад'): 'back_to_main'},
                                       sizes=(1,1))) # type: ignore
    await state.update_data(last_message_id=new_message.message_id)
    await callback_query.answer()

    analytics = workflow_data['analytics']
    await analytics(user_id=user_id,
                    category_name="/info",
                    command_name="/about_test")

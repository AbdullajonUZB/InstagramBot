import unittest

from keyboards.main_menu import main_menu


class MainMenuKeyboardTests(unittest.TestCase):
    def test_admin_panel_is_available_only_to_admin_menu(self):
        user_buttons = [button.text for row in main_menu("ru").keyboard for button in row]
        admin_buttons = [button.text for row in main_menu("ru", include_admin=True).keyboard for button in row]

        self.assertNotIn("🛠 Админ-панель", user_buttons)
        self.assertIn("🛠 Админ-панель", admin_buttons)
        self.assertIn("💎 Купить Premium", admin_buttons)

    def test_main_menu_actions_are_arranged_in_compact_rows(self):
        admin_rows = [[button.text for button in row] for row in main_menu("ru", include_admin=True).keyboard]
        user_rows = [[button.text for button in row] for row in main_menu("ru").keyboard]

        self.assertEqual(admin_rows, [
            ["📥 Скачать", "📜 История"],
            ["🎵 Видео → MP3", "👤 Профиль"],
            ["💎 Купить Premium", "⚙ Настройки"],
            ["ℹ️ Помощь", "🛠 Админ-панель"],
        ])
        self.assertEqual(user_rows[-1], ["ℹ️ Помощь"])


if __name__ == "__main__":
    unittest.main()

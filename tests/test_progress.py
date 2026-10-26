import io
import unittest

from monotile.progress import Bar, note


class Tty(io.StringIO):
    def isatty(self):
        return True


class Progress(unittest.TestCase):
    def test_bar_in_a_terminal(self):
        out = Tty()
        bar = Bar("Monotile-Circle-Dark", 4, stream=out)
        for _ in range(4):
            bar.step()
        bar.close()
        text = out.getvalue()
        self.assertIn("Monotile-Circle-Dark", text)
        self.assertIn("100%", text)
        self.assertIn("4/4", text)
        self.assertTrue(text.endswith("\n"))

    def test_silent_without_a_terminal(self):
        out = io.StringIO()
        bar = Bar("x", 10, stream=out)
        bar.step(10)
        bar.close()
        note("scanning", stream=out)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

"""Entry point: python -m mcp_installer"""
from mcp_installer.path_manager import set_dpi_awareness

# Set DPI awareness BEFORE any tkinter imports
set_dpi_awareness()

from mcp_installer.app import InstallerApp  # noqa: E402


def main():
    app = InstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

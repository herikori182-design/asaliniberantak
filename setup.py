#!/usr/bin/env python3
"""
Setup and Installation Script for Trading Research System
=========================================================

This script helps users set up the trading research system by:
1. Checking system requirements
2. Creating virtual environment
3. Installing dependencies
4. Setting up configuration files
5. Running initial tests
"""

import sys
import subprocess
import os
from pathlib import Path
import platform


class SetupManager:
    """Manages the setup process for the trading research system"""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.venv_path = self.project_root / "venv"
        self.requirements_file = self.project_root / "requirements.txt"
        self.env_example = self.project_root / ".env.example"
        self.env_file = self.project_root / ".env"

    def print_header(self, title):
        """Print a formatted header"""
        print("\n" + "=" * 60)
        print(f"  {title}")
        print("=" * 60 + "\n")

    def print_step(self, step, description):
        """Print a step description"""
        print(f"[{step}] {description}")

    def check_python_version(self):
        """Check if Python version is compatible"""
        self.print_step("1", "Checking Python version...")

        version = sys.version_info
        min_version = (3, 9)

        if version < min_version:
            print(f"  ✗ Python {version.major}.{version.minor} detected")
            print(f"  ✗ Python {min_version[0]}.{min_version[1]} or higher required")
            return False

        print(f"  ✓ Python {version.major}.{version.minor}.{version.micro} detected")
        return True

    def create_virtual_environment(self):
        """Create Python virtual environment"""
        self.print_step("2", "Creating virtual environment...")

        if self.venv_path.exists():
            print(f"  ✓ Virtual environment already exists at {self.venv_path}")
            return True

        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_path)],
                check=True,
                capture_output=True
            )
            print(f"  ✓ Virtual environment created at {self.venv_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to create virtual environment: {e}")
            return False

    def get_pip_command(self):
        """Get the appropriate pip command for the current platform"""
        if platform.system() == "Windows":
            return str(self.venv_path / "Scripts" / "pip")
        else:
            return str(self.venv_path / "bin" / "pip")

    def install_dependencies(self):
        """Install project dependencies"""
        self.print_step("3", "Installing dependencies...")

        if not self.requirements_file.exists():
            print(f"  ✗ requirements.txt not found at {self.requirements_file}")
            return False

        pip_command = self.get_pip_command()

        try:
            result = subprocess.run(
                [pip_command, "install", "-r", str(self.requirements_file)],
                check=True,
                capture_output=True,
                text=True
            )
            print("  ✓ Dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to install dependencies: {e}")
            print(f"  Error output: {e.stderr}")
            return False

    def setup_environment_file(self):
        """Setup .env file from .env.example"""
        self.print_step("4", "Setting up environment configuration...")

        if not self.env_example.exists():
            print(f"  ✗ .env.example not found at {self.env_example}")
            return False

        if self.env_file.exists():
            overwrite = input("  .env file already exists. Overwrite? (y/n): ").strip().lower()
            if overwrite != 'y':
                print("  ✓ Keeping existing .env file")
                return True

        try:
            # Copy .env.example to .env
            import shutil
            shutil.copy(self.env_example, self.env_file)
            print(f"  ✓ Created .env file from .env.example")
            print("  ⚠ IMPORTANT: Edit .env and add your INFOWAY_API_KEY")
            return True
        except Exception as e:
            print(f"  ✗ Failed to create .env file: {e}")
            return False

    def create_directories(self):
        """Create necessary directories"""
        self.print_step("5", "Creating project directories...")

        directories = [
            self.project_root / "data" / "cache",
            self.project_root / "logs",
            self.project_root / "strategies",
            self.project_root / "examples",
            self.project_root / "tests",
        ]

        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                print(f"  ✓ Created {directory.relative_to(self.project_root)}")
            except Exception as e:
                print(f"  ✗ Failed to create {directory}: {e}")
                return False

        return True

    def verify_installation(self):
        """Verify that the installation is working"""
        self.print_step("6", "Verifying installation...")

        # Test imports
        test_code = """
import sys
sys.path.insert(0, '.')

try:
    import engine
    print("  ✓ engine module imported successfully")
except ImportError as e:
    print(f"  ✗ Failed to import engine: {e}")
    sys.exit(1)

try:
    from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams
    print("  ✓ Strategy components imported successfully")
except ImportError as e:
    print(f"  ✗ Failed to import strategy components: {e}")
    sys.exit(1)

print("\\n✓ Installation verification passed!")
"""

        try:
            pip_command = self.get_pip_command()
            python_command = str(self.venv_path / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python"))

            result = subprocess.run(
                [python_command, "-c", test_code],
                capture_output=True,
                text=True,
                cwd=str(self.project_root)
            )

            print(result.stdout)
            if result.returncode != 0:
                print(result.stderr)
                return False

            return True
        except Exception as e:
            print(f"  ✗ Verification failed: {e}")
            return False

    def print_next_steps(self):
        """Print next steps for the user"""
        self.print_header("Setup Complete! Next Steps:")

        print("1. Edit the .env file and add your Infoway API key:")
        print("   INFOWAY_API_KEY=your_actual_api_key_here")
        print()

        print("2. Activate the virtual environment:")
        if platform.system() == "Windows":
            print("   venv\\Scripts\\activate")
        else:
            print("   source venv/bin/activate")
        print()

        print("3. Fetch market data:")
        print("   python examples/data_fetch_example.py")
        print()

        print("4. Run strategy examples:")
        print("   python examples/strategy_example.py")
        print()

        print("5. Create your own strategies and start researching!")
        print()

        print("For more information, see README.md")
        print()

    def run(self):
        """Run the complete setup process"""
        self.print_header("Trading Research System Setup")

        steps = [
            self.check_python_version,
            self.create_virtual_environment,
            self.install_dependencies,
            self.setup_environment_file,
            self.create_directories,
            self.verify_installation,
        ]

        for step in steps:
            if not step():
                print("\n✗ Setup failed. Please fix the errors above and try again.")
                return False

        self.print_next_steps()
        return True


def main():
    """Main entry point"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║           Trading Research System Setup Wizard                  ║
║                                                                ║
║  Professional-grade trading strategy research and backtesting  ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
    """)

    setup = SetupManager()

    try:
        success = setup.run()
        if success:
            print("✓ Setup completed successfully!")
            return 0
        else:
            print("✗ Setup failed. Please check the errors above.")
            return 1
    except KeyboardInterrupt:
        print("\n\n✗ Setup cancelled by user.")
        return 1
    except Exception as e:
        print(f"\n\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

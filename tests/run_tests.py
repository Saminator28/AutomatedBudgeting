#!/usr/bin/env python3
"""
Main test runner for AutomatedBudgeting test suite.

Run all tests with:
    python tests/run_tests.py

Run specific test module:
    python tests/run_tests.py test_parser

Run with verbose output:
    python tests/run_tests.py -v
"""

import unittest
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_all_tests(verbose=False):
    """
    Discover and run all tests in the tests directory.
    
    Args:
        verbose: Whether to run in verbose mode
    
    Returns:
        TestResult object
    """
    print("=" * 70)
    print("AutomatedBudgeting Test Suite")
    print("=" * 70)
    print()
    
    # Discover all test files
    loader = unittest.TestLoader()
    start_dir = Path(__file__).parent
    suite = loader.discover(str(start_dir), pattern='test_*.py')
    
    # Count tests
    test_count = suite.countTestCases()
    print(f"Found {test_count} test(s)\n")
    
    # Run tests
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    
    start_time = time.time()
    result = runner.run(suite)
    elapsed = time.time() - start_time
    
    # Print summary
    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print(f"Time elapsed: {elapsed:.2f}s")
    print("=" * 70)
    
    # Exit with appropriate code
    if result.wasSuccessful():
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1


def run_specific_test(test_name, verbose=False):
    """
    Run a specific test module.
    
    Args:
        test_name: Name of test module (e.g., 'test_parser')
        verbose: Whether to run in verbose mode
    
    Returns:
        TestResult object
    """
    print(f"Running {test_name}...\n")
    
    # Load specific test module
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(test_name)
    
    # Run tests
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print(f"\n✅ {test_name} passed!")
        return 0
    else:
        print(f"\n❌ {test_name} failed!")
        return 1


def print_usage():
    """Print usage information."""
    print("""
Usage:
    python tests/run_tests.py              Run all tests
    python tests/run_tests.py -v           Run all tests (verbose)
    python tests/run_tests.py test_parser  Run specific test module
    python tests/run_tests.py -h           Show this help message

Available test modules:
    test_parser       - Transaction line parsing tests
    test_categorizer  - AI categorization tests
    test_workflow     - Workflow integration tests
    test_config       - Configuration file tests
""")


def main():
    """Main entry point."""
    args = sys.argv[1:]
    
    # Check for help flag
    if '-h' in args or '--help' in args:
        print_usage()
        return 0
    
    # Check for verbose flag
    verbose = '-v' in args or '--verbose' in args
    if verbose:
        args = [a for a in args if a not in ['-v', '--verbose']]
    
    # Run tests
    if not args:
        # No arguments - run all tests
        return run_all_tests(verbose=verbose)
    else:
        # Specific test module
        test_name = args[0]
        if not test_name.startswith('test_'):
            test_name = f'test_{test_name}'
        
        try:
            return run_specific_test(test_name, verbose=verbose)
        except (ImportError, AttributeError) as e:
            print(f"Error: Could not load test module '{test_name}'")
            print(f"Details: {e}")
            print()
            print_usage()
            return 1


if __name__ == '__main__':
    sys.exit(main())

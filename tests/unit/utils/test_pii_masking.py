"""
Unit tests for PII Masking Utility.

Test IDs from PII_Exposure_Control_Policy.md:
- PII-UNIT-001 through PII-UNIT-005 (partial coverage)

Bead: 5O (fundus_img_xtract-r4o)
"""

import pytest
from utils.pii_masking import (
    mask_patient_id,
    mask_patient_name,
    mask_phone,
    mask_email,
    mask_username,
    should_mask_pii,
    mask_dict_pii,
    strip_pii_from_dict,
)


class TestMaskPatientId:
    """Tests for mask_patient_id function."""
    
    def test_normal_patient_id(self):
        """Standard patient ID should show last 3 chars."""
        assert mask_patient_id("12345678") == "P****678"
    
    def test_short_patient_id(self):
        """Short patient IDs should be fully masked."""
        assert mask_patient_id("AB") == "P***"
        assert mask_patient_id("123") == "P***"
    
    def test_none_patient_id(self):
        """None should return masked placeholder."""
        assert mask_patient_id(None) == "P***"
    
    def test_empty_patient_id(self):
        """Empty string should return masked placeholder."""
        assert mask_patient_id("") == "P***"
    
    def test_exact_length(self):
        """ID exactly at threshold should be masked."""
        assert mask_patient_id("1234") == "P****234"
    
    def test_custom_show_last(self):
        """Custom show_last parameter should work."""
        assert mask_patient_id("12345678", show_last=4) == "P****5678"
    
    def test_integer_patient_id(self):
        """Integer patient IDs should be converted and masked."""
        assert mask_patient_id(12345678) == "P****678"


class TestMaskPatientName:
    """Tests for mask_patient_name function."""
    
    def test_always_anonymous(self):
        """Patient name should always return Anonymous."""
        assert mask_patient_name("John Doe") == "Anonymous"
    
    def test_none_input(self):
        """None should still return Anonymous."""
        assert mask_patient_name(None) == "Anonymous"
    
    def test_empty_string(self):
        """Empty string should still return Anonymous."""
        assert mask_patient_name("") == "Anonymous"


class TestMaskPhone:
    """Tests for mask_phone function."""
    
    def test_standard_phone(self):
        """Standard 10-digit phone should show last 4."""
        assert mask_phone("1234567890") == "***-***-7890"
    
    def test_formatted_phone(self):
        """Formatted phone should extract digits and mask."""
        assert mask_phone("+1-555-123-4567") == "***-***-4567"
        assert mask_phone("(555) 123-4567") == "***-***-4567"
    
    def test_short_phone(self):
        """Short phone numbers should be fully masked."""
        assert mask_phone("123") == "***-****"
    
    def test_none_phone(self):
        """None should return masked placeholder."""
        assert mask_phone(None) == "***-****"
    
    def test_empty_phone(self):
        """Empty string should return masked placeholder."""
        assert mask_phone("") == "***-****"


class TestMaskEmail:
    """Tests for mask_email function."""
    
    def test_standard_email(self):
        """Standard email should show first 2 chars and domain."""
        assert mask_email("john.doe@hospital.org") == "jo***@hospital.org"
    
    def test_simple_email(self):
        """Simple email should work."""
        assert mask_email("admin@example.com") == "ad***@example.com"
    
    def test_short_local_part(self):
        """Short local part should show all chars."""
        assert mask_email("a@test.com") == "a***@test.com"
    
    def test_no_at_sign(self):
        """Invalid email without @ should be fully masked."""
        assert mask_email("invalid") == "***@***.com"
    
    def test_none_email(self):
        """None should return masked placeholder."""
        assert mask_email(None) == "***@***.com"
    
    def test_empty_email(self):
        """Empty string should return masked placeholder."""
        assert mask_email("") == "***@***.com"


class TestMaskUsername:
    """Tests for mask_username function."""
    
    def test_standard_username(self):
        """Standard username should show first 2 chars."""
        assert mask_username("johndoe") == "jo***"
    
    def test_short_username(self):
        """Short username should show all chars with mask suffix."""
        assert mask_username("ab") == "ab***"
        assert mask_username("a") == "a***"
    
    def test_none_username(self):
        """None should return masked placeholder."""
        assert mask_username(None) == "***"
    
    def test_custom_show_first(self):
        """Custom show_first parameter should work."""
        assert mask_username("johndoe", show_first=3) == "joh***"


class TestShouldMaskPii:
    """Tests for should_mask_pii function."""
    
    def test_different_hospitals(self):
        """Different hospitals should require masking."""
        assert should_mask_pii(1, 2) is True
    
    def test_same_hospital(self):
        """Same hospital should not require masking."""
        assert should_mask_pii(1, 1) is False
    
    def test_no_user_hospital(self):
        """No user hospital should require masking."""
        assert should_mask_pii(None, 1) is True
    
    def test_no_data_hospital(self):
        """No data hospital should require masking."""
        assert should_mask_pii(1, None) is True
    
    def test_resident_role_always_masked(self):
        """Resident role should always be masked."""
        assert should_mask_pii(1, 1, 'resident') is True
    
    def test_resident2_role_always_masked(self):
        """Resident2 role should always be masked."""
        assert should_mask_pii(1, 1, 'resident2') is True
    
    def test_ophthalmologist_role_always_masked(self):
        """Ophthalmologist role should always be masked."""
        assert should_mask_pii(1, 1, 'ophthalmologist') is True
    
    def test_optometrist_same_hospital_not_masked(self):
        """Optometrist at same hospital should see PII."""
        assert should_mask_pii(1, 1, 'optometrist') is False
    
    def test_admin_same_hospital_not_masked(self):
        """Admin at same hospital should see PII."""
        assert should_mask_pii(1, 1, 'admin') is False
    
    def test_custom_always_mask_roles(self):
        """Custom always_mask_roles should work."""
        assert should_mask_pii(1, 1, 'custom_role', ['custom_role']) is True


class TestMaskDictPii:
    """Tests for mask_dict_pii function."""
    
    def test_mask_patient_fields(self):
        """Should mask patient_name and patient_id."""
        data = {'patient_name': 'John Doe', 'patient_id': '12345678', 'uuid': 'abc-123'}
        result = mask_dict_pii(data)
        
        assert result['patient_name'] == 'Anonymous'
        assert result['patient_id'] == 'P****678'
        assert result['uuid'] == 'abc-123'  # Unchanged
    
    def test_mask_contact_fields(self):
        """Should mask phone and email."""
        data = {'phone': '1234567890', 'email': 'test@example.com'}
        result = mask_dict_pii(data)
        
        assert result['phone'] == '***-***-7890'
        assert result['email'] == 'te***@example.com'
    
    def test_empty_dict(self):
        """Empty dict should return empty dict."""
        assert mask_dict_pii({}) == {}
    
    def test_none_input(self):
        """None input should return None."""
        assert mask_dict_pii(None) is None
    
    def test_no_pii_fields(self):
        """Dict without PII fields should be unchanged."""
        data = {'uuid': 'abc', 'status': 'active'}
        result = mask_dict_pii(data)
        
        assert result == data


class TestStripPiiFromDict:
    """Tests for strip_pii_from_dict function."""
    
    def test_strip_patient_fields(self):
        """Should remove patient_name and patient_id."""
        data = {'patient_name': 'John', 'uuid': 'abc-123'}
        result = strip_pii_from_dict(data)
        
        assert 'patient_name' not in result
        assert result['uuid'] == 'abc-123'
    
    def test_strip_multiple_pii_fields(self):
        """Should remove all default PII fields."""
        data = {
            'patient_name': 'John',
            'patient_id': '123',
            'phone': '555-1234',
            'email': 'test@test.com',
            'uuid': 'abc'
        }
        result = strip_pii_from_dict(data)
        
        assert 'patient_name' not in result
        assert 'patient_id' not in result
        assert 'phone' not in result
        assert 'email' not in result
        assert result['uuid'] == 'abc'
    
    def test_custom_pii_fields(self):
        """Should use custom PII field list."""
        data = {'custom_field': 'sensitive', 'safe_field': 'ok'}
        result = strip_pii_from_dict(data, pii_fields=['custom_field'])
        
        assert 'custom_field' not in result
        assert result['safe_field'] == 'ok'
    
    def test_empty_dict(self):
        """Empty dict should return empty dict."""
        assert strip_pii_from_dict({}) == {}
    
    def test_none_input(self):
        """None input should return None."""
        assert strip_pii_from_dict(None) is None

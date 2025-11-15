from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import fitz
from PIL import Image
import io
import json
import re
import base64
from datetime import datetime
import tempfile
import unicodedata
import requests
import time
from bnunicodenormalizer import Normalizer
import bangla

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialize normalizer
normalizer = Normalizer()

# Try to get spell checker
try:
    from bangla.spell import check as spell_check
    SPELL_CHECK_AVAILABLE = True
except ImportError:
    SPELL_CHECK_AVAILABLE = False
    print("Warning: bangla.spell module not available, using basic cleaning only")

def clean_bangla_text(text):
    """Clean and normalize Bengali text"""
    if not text:
        return text
        
    try:
        text = str(text)
        
        # Split text into words while preserving delimiters
        parts = re.split(r'([,\s/\-\+])', text)
        cleaned_parts = []
        
        for part in parts:
            if not part.strip():
                cleaned_parts.append(part)
                continue
                
            # Only process parts with Bengali characters
            if re.search(r'[ঀ-৿]', part):
                # Step 1: Try normalizer on individual word
                try:
                    normalized = normalizer(part)
                    if normalized:
                        part = normalized['normalized']
                except:
                    pass
                
                # Step 2: Fix common OCR errors (optimized order)
                # Fix combined errors first to avoid redundancy
                part = part.replace('ুুে', 'ে')  # Combined first
                part = part.replace('ংং', 'ং')
                part = part.replace('াা', 'া')
                part = part.replace('ীী', 'ী')
                part = part.replace('ুু', 'ু')
                part = part.replace('ূূ', 'ূ')
                
          
                # Step 5: Apply spell check if available
                if SPELL_CHECK_AVAILABLE:
                    try:
                        corrected = spell_check(part)
                        if corrected:
                            part = corrected[0]
                    except:
                        pass
            
            cleaned_parts.append(part)
        
        text = ''.join(cleaned_parts)
        
        # Clean up spaces and punctuation
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[:,]\s*', ': ', text)
        text = re.sub(r'\s*ঃ\s*', 'ঃ ', text)
        
        return text.strip()
        
    except Exception as e:
        print(f"Error in clean_bangla_text: {str(e)}")
        return text

def normalize_all_fields(data):
    """Apply text cleaning to all Bengali text fields"""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                # Check if the field contains Bengali text
                if re.search(r'[ঀ-৿]', value):
                    data[key] = clean_bangla_text(value)
            elif isinstance(value, dict):
                data[key] = normalize_all_fields(value)
    return data

def remove_background(image_base64):
    """Remove background from image using Bria API."""
    api_token = "600651f9d8f84aa3a00607c1108a2871"
    
    try:
        # Step 1: Send POST request to remove background
        response = requests.post(
            'https://engine.prod.bria-api.com/v2/image/edit/remove_background',
            json={'image': image_base64},
            headers={
                'Content-Type': 'application/json',
                'api_token': api_token
            },
            timeout=30
        )
        
        print(f"Background removal initial response: {response.status_code}")
        
        # API returns 202 (Accepted) for background removal request
        if response.status_code not in [200, 202]:
            print(f"Error response: {response.text}")
            return None
        
        response_data = response.json()
        status_url = response_data.get('status_url')
        
        print(f"Status URL: {status_url}")
        if not status_url:
            print("No status URL received")
            return None
        
        # Step 2: Poll status_url until COMPLETED
        max_attempts = 60  # 3 minutes max
        attempts = 0
        
        while attempts < max_attempts:
            status_response = requests.get(
                status_url,
                headers={
                    'Content-Type': 'application/json',
                    'api_token': api_token
                },
                timeout=30
            )
            
            if status_response.status_code != 200:
                print(f"Status check failed with code: {status_response.status_code}")
                return None
            
            status_data = status_response.json()
            
            print(f"Status check {attempts + 1} - Full response: {json.dumps(status_data, indent=2)}")
            
            if status_data.get('status') == 'COMPLETED':
                # Image URL is nested in result object
                image_url = status_data.get('result', {}).get('image_url')
                print(f"Image URL received: {image_url}")
                if image_url:
                    # Download the processed image
                    img_response = requests.get(image_url, timeout=30)
                    if img_response.status_code == 200:
                        # Convert to base64
                        img_base64 = base64.b64encode(img_response.content).decode('utf-8')
                        print(f"Successfully converted image, length: {len(img_base64)}")
                        return img_base64
                return None
            
            time.sleep(3)
            attempts += 1
        
        return None
        
    except Exception as e:
        print(f"Background removal error: {str(e)}")
        return None

def convert_to_bangla_number(text):
    """Convert English numbers to Bengali numbers in text."""
    if not text:
        return text
    number_map = {
        '0': '০', '1': '১', '2': '২', '3': '৩', '4': '৪',
        '5': '৫', '6': '৬', '7': '৭', '8': '৮', '9': '৯'
    }
    result = str(text)
    for english, bangla in number_map.items():
        result = result.replace(english, bangla)
    return result

def convert_english_to_bangla(text):
    """Convert English letters and numbers to Bengali."""
    if not text:
        return text
        
    letter_map = {
        'A': 'এ', 'B': 'বি', 'C': 'সি', 'D': 'ডি', 'E': 'ই',
        'F': 'এফ', 'G': 'জি', 'H': 'এইচ', 'I': 'আই', 'J': 'জে',
        'K': 'কে', 'L': 'এল', 'M': 'এম', 'N': 'এন', 'O': 'ও',
        'P': 'পি', 'Q': 'কিউ', 'R': 'আর', 'S': 'এস', 'T': 'টি',
        'U': 'ইউ', 'V': 'ভি', 'W': 'ডব্লিউ', 'X': 'এক্স', 'Y': 'ওয়াই',
        'Z': 'জেড',
        'a': 'এ', 'b': 'বি', 'c': 'সি', 'd': 'ডি', 'e': 'ই',
        'f': 'এফ', 'g': 'জি', 'h': 'এইচ', 'i': 'আই', 'j': 'জে',
        'k': 'কে', 'l': 'এল', 'm': 'এম', 'n': 'এন', 'o': 'ও',
        'p': 'পি', 'q': 'কিউ', 'r': 'আর', 's': 'এস', 't': 'টি',
        'u': 'ইউ', 'v': 'ভি', 'w': 'ডব্লিউ', 'x': 'এক্স', 'y': 'ওয়াই',
        'z': 'জেড'
    }

    # First convert English letters
    result = ''
    i = 0
    while i < len(text):
        if text[i] in letter_map:
            result += letter_map[text[i]]
        else:
            result += text[i]
        i += 1

    # Then convert numbers
    return convert_to_bangla_number(result)

def parse_nid_text(text):
    """Parse National ID card text into structured JSON format."""
    data = {}
    
    # First normalize the entire text
    text = clean_bangla_text(text)
    
    # Extract NID
    nid_match = re.search(r'National ID\s*(\d+)', text)
    if nid_match:
        data['nid'] = nid_match.group(1)
    
    # Extract PIN
    pin_match = re.search(r'Pin\s*(\d+)', text)
    if pin_match:
        data['pin'] = pin_match.group(1)
    
    # Extract Form No
    form_match = re.search(r'Form No\s*(\d+)', text)
    if form_match:
        data['formNo'] = form_match.group(1)
    
    # Extract Sl No
    sl_match = re.search(r'Sl No\s*(\d+)', text)
    if sl_match:
        data['sl_no'] = sl_match.group(1)
    
    # Extract Father NID
    father_nid_match = re.search(r'NID Father\s*(\d+)', text)
    if father_nid_match:
        data['father_nid'] = father_nid_match.group(1)
    
    # Extract Mother NID
    mother_nid_match = re.search(r'NID Mother\s*(\d+)', text)
    if mother_nid_match:
        data['mother_nid'] = mother_nid_match.group(1)
    
    # Extract Religion
    religion_match = re.search(r'Religion\s*(\w+)', text)
    if religion_match:
        data['religion'] = religion_match.group(1)
    
    # Extract Mobile
    mobile_match = re.search(r'Mobile\s*(\d+)', text)
    if mobile_match:
        data['mobile'] = mobile_match.group(1)
    
    # Extract Voter No
    voter_match = re.search(r'Voter No\s*(\d+)', text)
    if voter_match:
        data['voterNo'] = voter_match.group(1)
    
    # Extract Voter Area
    voter_area_match = re.search(r'Voter Area\s*(.+?)(?:\s+Voter\s+At|Smart Card|\n|$)', text)
    if voter_area_match:
        voter_area = voter_area_match.group(1).strip()
        # Clean up any remaining metadata text
        voter_area = re.sub(r'\s*(Voter At.*|Smart Card.*|permanent.*)$', '', voter_area)
        data['voterArea'] = clean_bangla_text(voter_area)
    
    # Extract Education
    education_match = re.search(r'Education\s*(.+?)(?:\n|Education|Smart Card|BIRTH_CERTIFICATE|VOTER)', text)
    if education_match:
        education = education_match.group(1).strip()
        # Clean up the education field
        education = re.sub(r'\s*(Smart Card.*|BIRTH_CERTIFICATE.*|VOTER.*)$', '', education)
        data['education'] = clean_bangla_text(education)

    # Extract Occupation
    occupation_match = re.search(r'Occupation\s*(.+?)(?:\n|Disability)', text)
    if occupation_match:
        data['occupation'] = occupation_match.group(1).strip()    # Extract Status
    status_match = re.search(r'Status\s*(\w+)', text)
    if status_match:
        data['status'] = status_match.group(1)
    
    # Extract Name (Bangla)
    name_bangla_match = re.search(r'Name\(Bangla\)\s*(.+?)(?:\n|Name)', text)
    if name_bangla_match:
        data['nameBangla'] = name_bangla_match.group(1).strip()
    
    # Extract Name (English)
    name_english_match = re.search(r'Name\(English\)\s*(.+?)(?:\n|Date)', text)
    if name_english_match:
        data['nameEnglish'] = name_english_match.group(1).strip()
    
    # Extract Date of Birth
    dob_match = re.search(r'Date of Birth\s*(\d{4}-\d{2}-\d{2})', text)
    if dob_match:
        dob = datetime.strptime(dob_match.group(1), '%Y-%m-%d')
        data['dateOfBirth'] = dob.strftime('%d %b %Y')
    
    # Extract Birth Place
    birth_place_match = re.search(r'Birth Place\s*(.+?)(?:\n|Birth)', text)
    if birth_place_match:
        data['birthPlace'] = birth_place_match.group(1).strip()
    
    # Extract Father Name
    father_match = re.search(r'Father Name\s*(.+?)(?:\n|Mother)', text)
    if father_match:
        data['fatherName'] = father_match.group(1).strip()
    
    # Extract Mother Name
    mother_match = re.search(r'Mother\s*Name\s*(.+?)(?:\n|Spouse)', text)
    if mother_match:
        data['motherName'] = mother_match.group(1).strip()
    
    # Extract Spouse Name
    spouse_match = re.search(r'Spouse\s*Name\s*([^G\n].*?)(?:\n|Gender|$)', text)
    if spouse_match:
        spouse_name = spouse_match.group(1).strip()
        # Double check that we didn't capture "Gender" somehow
        data['spouseName'] = "" if spouse_name.startswith("Gender") else spouse_name
    else:
        data['spouseName'] = ""
    
    # Extract Gender
    gender_match = re.search(r'Gender\s*(\w+)', text)
    if gender_match:
        data['gender'] = gender_match.group(1)
    
    # Extract Blood Group
    blood_match = re.search(r'Blood Group\s*(.+?)(?:\n|TIN)', text)
    if blood_match:
        blood = blood_match.group(1).strip()
        data['bloodGroup'] = blood if blood and blood != 'TIN' else ""
    else:
        data['bloodGroup'] = ""
    
    # Parse Present Address
    home_holding_match = re.search(r'Present\s+Address.*?Home/Holding\s*No\s*(.*?)(?=(?:Village|Post\s*Office|Post|Additional|\n\n|$))', text, re.DOTALL | re.I)
    village_match = re.search(r'Present\s+Address.*?(?:Village/Road)[:\s]*?(.*?)(?=(?:Home|Additional|Mouza|\n\n|$))', text, re.DOTALL | re.I)
    additional_village_match = re.search(r'Present\s+Address.*?Additional\s+Village/Road[:\s]*?(.*?)(?=(?:Home|Mouza|\n\n|$))', text, re.DOTALL | re.I)
    mouza_match = re.search(r'Present\s+Address.*?Mouza/Moholla\s*(.*?)(?=(?:Ward|Additional|Union|\n\n))', text, re.DOTALL | re.I)
    city_corporation_match = re.search(r'City\s*Corporation\s*Or\s*Municipality\s*(.*?)(?=(?:Post|Union|Upozila|District|Division|Region|\n\n))', text, re.DOTALL | re.I)
    additional_mouza_match = re.search(r'Present\s+Address.*?Additional\s*Mouza/Moholla\s*(.*?)(?=(?:Ward|Union|\n\n))', text, re.DOTALL | re.I)
    union_match = re.search(r'Present\s+Address.*?Union/Ward\s*(.*?)(?=(?:Mouza|Post|City|\n\n))', text, re.DOTALL | re.I)
    post_office_match = re.search(r'Present\s+Address.*?Post\s*Office\s*(.*?)(?=(?:Postal|City|\n\n))', text, re.DOTALL | re.I)
    postal_code_match = re.search(r'Present\s+Address.*?Postal\s*Code\s*(.*?)(?=(?:Region|City|\n\n))', text, re.DOTALL | re.I)
    upozila_match = re.search(r'Present\s+Address.*?Upozila\s*(.*?)(?=(?:Union|Post|City|\n\n))', text, re.DOTALL | re.I)
    district_match = re.search(r'Present\s+Address.*?District\s*(.*?)(?=(?:RMO|Division|City|\n\n))', text, re.DOTALL | re.I)
    region_match = re.search(r'Present\s+Address.*?Region\s*(.*?)(?=(?:Permanent|Division|\n\n))', text, re.DOTALL | re.I)
    division_match = re.search(r'Present\s+Address.*?Division\s*(.*?)(?=(?:District|Region|City|\n\n))', text, re.DOTALL | re.I)

    present_parts = []

    # helper: clean and join multiline values
    def clean_and_join_value(match):
        if not match:
            return ''
        value = match.group(1)
        if not value:
            return ''
        # Join multiple lines and clean up
        value = ' '.join(line.strip() for line in value.split('\n') if line.strip())
        # Remove common stray leading labels
        value = re.sub(r'^(?:Additional|Village/Road|Village|Mouza/Moholla|Mouza)[:\s\-\–\—]*', '', value, flags=re.I)
        # Clean up punctuation and spaces
        value = re.sub(r'^[\s\:\-\,]+', '', value)
        value = re.sub(r'\s{2,}', ' ', value)
        return value.strip()

    # Process Home/Holding
    home_val = clean_and_join_value(home_holding_match)
    home_val = convert_english_to_bangla(home_val) if home_val else ''
    if home_val:
        present_parts.append(f"বাসা/হোল্ডিংঃ {home_val}")

    # helper: clean OCR'd captures (for backward compatibility)
    def clean_field(s):
        if not s:
            return ''
        s = s.strip()
        s = re.sub(r'^(?:Additional|Village/Road|Village|Mouza/Moholla|Mouza)[:\s\-\–\—]*', '', s, flags=re.I)
        s = re.sub(r'^[\s\:\-\,]+', '', s)
        s = re.sub(r'\s{2,}', ' ', s)
        return s

    # Process Village/Road with fallbacks
    village_raw = clean_and_join_value(village_match)
    add_village_raw = clean_and_join_value(additional_village_match)
    mouza_raw = clean_and_join_value(mouza_match)
    union_raw = clean_and_join_value(union_match)
    
    village_val = (village_raw or add_village_raw or mouza_raw or union_raw)
    present_parts.append(f"গ্রাম/রাস্তাঃ {village_val or ' '}")

    # Process Mouza/Moholla with fallback
    mouza_val = clean_and_join_value(mouza_match)
    add_mouza_val = clean_and_join_value(additional_mouza_match)
    
    if mouza_val or add_mouza_val:
        final_mouza = mouza_val or add_mouza_val
        if not final_mouza.lower().startswith('ward'):
            present_parts.append(f"মৌজা/মহল্লাঃ {final_mouza}")
    else:
        present_parts.append(f"মৌজা/মহল্লাঃ {' '}")

    # Process remaining fields
    union_val = clean_and_join_value(union_match)
    present_parts.append(f"ইউনিয়ন/ওয়ার্ডঃ {union_val or ' '}")

    post_office_val = clean_and_join_value(post_office_match)
    present_parts.append(f"পোষ্ট অফিসঃ {post_office_val or ' '}")

    postal_code_val = clean_and_join_value(postal_code_match)
    postal_code_val = convert_to_bangla_number(postal_code_val) if postal_code_val else ''
    present_parts.append(f"পোষ্ট কোডঃ {postal_code_val or ' '}")

    upozila_val = clean_and_join_value(upozila_match)
    upozila_val = convert_to_bangla_number(upozila_val) if upozila_val else ''
    present_parts.append(f"উপজেলাঃ {upozila_val or ' '}")

    district_val = clean_and_join_value(district_match)
    present_parts.append(f"জেলাঃ {district_val or ' '}")

    region_val = clean_and_join_value(region_match)
    present_parts.append(f"অঞ্চলঃ {region_val or ' '}")

    division_val = clean_and_join_value(division_match)
    present_parts.append(f"বিভাগঃ {division_val or ' '}")
    
    # Add City Corporation/Municipality only if value exists
    city_corporation_val = city_corporation_match.group(1).strip() if city_corporation_match else ''
    if city_corporation_val:
        # Join multiple lines with space and clean up extra spaces
        city_corporation_val = ' '.join(line.strip() for line in city_corporation_val.split('\n') if line.strip())
        if not any(city_corporation_val.lower().startswith(x) for x in ['upozila', 'union', 'district']):
            present_parts.append(f"সিটি কর্পোরেশন/পৌরসভাঃ {city_corporation_val}")

    data['presentAddress'] = ", ".join(present_parts)
    
    # Parse Permanent Address
    perm_home_holding_match = re.search(r'Permanent\s+Address.*?Home/Holding\s*No\s*(.*?)(?=(?:Village|Post\s*Office|Post|Additional|\n\n|$))', text, re.DOTALL | re.I)
    perm_village_match = re.search(r'Permanent\s+Address.*?(?:Village/Road)[:\s]*?(.*?)(?=(?:Home|Additional|Mouza|\n\n|$))', text, re.DOTALL | re.I)
    perm_additional_village_match = re.search(r'Permanent\s+Address.*?Additional\s+Village/Road[:\s]*?(.*?)(?=(?:Home|Mouza|\n\n|$))', text, re.DOTALL | re.I)
    perm_city_corporation_match = re.search(r'Permanent\s+Address.*?City\s*Corporation\s*Or\s*Municipality\s*(.*?)(?=(?:Post|Union|Upozila|District|Division|Region|\n\n))', text, re.DOTALL | re.I)
    perm_mouza_match = re.search(r'Permanent\s+Address.*?Mouza/Moholla\s*(.*?)(?=(?:Ward|Additional|Union|\n\n))', text, re.DOTALL | re.I)
    perm_additional_mouza_match = re.search(r'Permanent\s+Address.*?Additional\s*Mouza/Moholla\s*(.*?)(?=(?:Ward|Union|\n\n))', text, re.DOTALL | re.I)
    perm_union_match = re.search(r'Permanent\s+Address.*?Union/Ward\s*(.*?)(?=(?:Mouza|Post|City|\n\n))', text, re.DOTALL | re.I)
    perm_post_office_match = re.search(r'Permanent\s+Address.*?Post\s*Office\s*(.*?)(?=(?:Postal|City|\n\n))', text, re.DOTALL | re.I)
    perm_postal_code_match = re.search(r'Permanent\s+Address.*?Postal\s*Code\s*(.*?)(?=(?:Region|City|\n\n))', text, re.DOTALL | re.I)
    perm_upozila_match = re.search(r'Permanent\s+Address.*?Upozila\s*(.*?)(?=(?:Union|Post|City|\n\n))', text, re.DOTALL | re.I)
    perm_district_match = re.search(r'Permanent\s+Address.*?District\s*(.*?)(?=(?:RMO|Division|City|\n\n))', text, re.DOTALL | re.I)
    perm_region_match = re.search(r'Permanent\s+Address.*?Region\s*(.*?)(?=(?:Education|Division|\n\n))', text, re.DOTALL | re.I)
    perm_division_match = re.search(r'Permanent\s+Address.*?Division\s*(.*?)(?=(?:District|Region|City|Foreign|Smart Card|\n\n))', text, re.DOTALL | re.I)

    permanent_parts = []

    # Process Home/Holding
    phome_val = clean_and_join_value(perm_home_holding_match)
    phome_val = convert_english_to_bangla(phome_val) if phome_val else ''
    if phome_val:
        permanent_parts.append(f"বাসা/হোল্ডিংঃ {phome_val}")

    # Process Village/Road with fallbacks
    pvillage_raw = clean_and_join_value(perm_village_match)
    p_add_village_raw = clean_and_join_value(perm_additional_village_match)
    pmouza_raw = clean_and_join_value(perm_mouza_match)
    punion_raw = clean_and_join_value(perm_union_match)
    
    pvillage_val = (pvillage_raw or p_add_village_raw or pmouza_raw or punion_raw)
    permanent_parts.append(f"গ্রাম/রাস্তাঃ {pvillage_val or ' '}")

    # Process Mouza/Moholla with fallback
    pmouza_val = clean_and_join_value(perm_mouza_match)
    p_add_mouza_val = clean_and_join_value(perm_additional_mouza_match)
    
    if pmouza_val or p_add_mouza_val:
        final_pmouza = pmouza_val or p_add_mouza_val
        if not final_pmouza.lower().startswith('ward'):
            permanent_parts.append(f"মৌজা/মহল্লাঃ {final_pmouza}")
    else:
        permanent_parts.append(f"মৌজা/মহল্লাঃ {' '}")

    # Process remaining fields
    punion_val = clean_and_join_value(perm_union_match)
    permanent_parts.append(f"ইউনিয়ন/ওয়ার্ডঃ {punion_val or ' '}")

    ppost_office_val = clean_and_join_value(perm_post_office_match)
    permanent_parts.append(f"পোষ্ট অফিসঃ {ppost_office_val or ' '}")

    ppostal_code_val = clean_and_join_value(perm_postal_code_match)
    ppostal_code_val = convert_to_bangla_number(ppostal_code_val) if ppostal_code_val else ''
    permanent_parts.append(f"পোষ্ট কোডঃ {ppostal_code_val or ' '}")

    pupozila_val = clean_and_join_value(perm_upozila_match)
    pupozila_val = convert_to_bangla_number(pupozila_val) if pupozila_val else ''
    permanent_parts.append(f"উপজেলাঃ {pupozila_val or ' '}")

    pdistrict_val = clean_and_join_value(perm_district_match)
    permanent_parts.append(f"জেলাঃ {pdistrict_val or ' '}")

    pregion_val = clean_and_join_value(perm_region_match)
    permanent_parts.append(f"অঞ্চলঃ {pregion_val or ' '}")

    pdivision_val = clean_and_join_value(perm_division_match)
    permanent_parts.append(f"বিভাগঃ {pdivision_val or ' '}")
    
    # Add City Corporation/Municipality
    pcity_corporation_val = perm_city_corporation_match.group(1).strip() if perm_city_corporation_match else ''
    if pcity_corporation_val:
        # Join multiple lines with space and clean up extra spaces
        pcity_corporation_val = ' '.join(line.strip() for line in pcity_corporation_val.split('\n') if line.strip())
        if not any(pcity_corporation_val.lower().startswith(x) for x in ['upozila', 'union', 'district']):
            permanent_parts.append(f"সিটি কর্পোরেশন/পৌরসভাঃ {pcity_corporation_val}")

    # Clean up and join the address parts
    permanent_address = ", ".join(permanent_parts)
    
    # Remove any metadata and extra information
    permanent_address = re.sub(r'\s*(Foreign Address.*|Smart Card.*|BIRTH_CERTIFICATE.*|DATA ENTRY.*|VOTER FORM.*|City House.*|National ID.*|Death Date.*|$)', '', permanent_address)
    permanent_address = re.sub(r',\s*,+', ',', permanent_address)  # Remove multiple consecutive commas
    permanent_address = re.sub(r',\s*$', '', permanent_address)    # Remove trailing comma
    
    data['permanentAddress'] = permanent_address
    
    # Create simple address format
    simple_address_parts = []
    # Convert home value numbers if any
    home_val = convert_to_bangla_number(home_val) if home_val else ''
    if home_val:  # Only append if there's a value
        simple_address_parts.append(f"বাসা/হোল্ডিংঃ {home_val}")

    # Convert village value numbers if any
    village_val = convert_to_bangla_number(village_val) if village_val else ''
    simple_address_parts.append(f"গ্রাম/রাস্তা: {village_val}")
    
    # Handle post office and postal code
    post_office = clean_and_join_value(post_office_match)
    postal_code = clean_and_join_value(postal_code_match)
    if post_office or postal_code:
        post_office = convert_to_bangla_number(post_office)
        postal_code = convert_to_bangla_number(postal_code)
        post_text = f"ডাকঘর: {post_office}"
        if postal_code:
            post_text += f" - {postal_code}"
        simple_address_parts.append(post_text)
    
    # Add upazila and district with Bengali numbers
    if upozila_match:
        upazila_val = convert_to_bangla_number(upozila_match.group(1).strip())
        simple_address_parts.append(upazila_val)

    # Add City Corporation value before district if it exists
    if city_corporation_match:
        city_corp_val = clean_and_join_value(city_corporation_match)
        if city_corp_val and not any(city_corp_val.lower().startswith(x) for x in ['upozila', 'union', 'district']):
            simple_address_parts.append(city_corp_val)

    if district_match:
        district_val = convert_to_bangla_number(district_match.group(1).strip())
        simple_address_parts.append(district_val)
    
    data['address'] = ", ".join(x for x in simple_address_parts if x.split(': ')[-1].strip())
    
    return data


def get_image_dimensions(pil_image):
    """Get image dimensions and calculate size."""
    width, height = pil_image.size
    pixel_area = width * height
    return width, height, pixel_area

def classify_image(pil_image, width, height, pixel_area):
    """Classify whether image is photo or signature based on characteristics."""
    
    # Calculate aspect ratio
    aspect_ratio = width / height if height > 0 else 1
    
    # Photo characteristics:
    # - Larger size (>50000 pixels)
    # - Near-square or wider aspect ratio (0.8 to 1.3)
    # - More diverse colors
    
    # Signature characteristics:
    # - Smaller size (<30000 pixels)
    # - Taller/narrower aspect ratio (0.3 to 0.7)
    # - Mostly grayscale/black & white
    
    is_photo = False
    is_signature = False
    confidence = "Medium"
    
    if pixel_area > 50000:
        # Large image - likely photo
        if 0.7 < aspect_ratio < 1.5:
            is_photo = True
            confidence = "High"
        else:
            confidence = "Medium"
    elif 20000 < pixel_area < 50000:
        # Medium image
        if aspect_ratio < 0.7:
            is_signature = True
            confidence = "High"
        else:
            is_photo = True
            confidence = "Medium"
    else:
        # Small image - likely signature
        is_signature = True
        confidence = "High"
    
    return {
        "type": "photo" if is_photo else "signature" if is_signature else "unknown",
        "aspect_ratio": round(aspect_ratio, 2),
        "confidence": confidence,
        "pixel_area": pixel_area
    }

def extract_images_and_text_from_pdf(pdf_bytes):
    """Extract images and text from PDF bytes with classification."""
    
    # Open PDF from bytes
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    images_data = []  # Store with size info for sorting
    all_text = ""
    
    # Iterate through each page
    for page_num in range(len(pdf_document)):
        page = pdf_document[page_num]
        
        # Try multiple extraction methods for better Bangla support
        try:
            # Method 1: Extract with blocks (better Unicode handling)
            blocks = page.get_text("dict")["blocks"]
            page_text = ""
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            page_text += span["text"]
                        page_text += "\n"
        except:
            # Fallback to standard method
            page_text = page.get_text("text")
        
        # Normalize Unicode to composed form (NFC) for Bangla
        page_text = unicodedata.normalize('NFC', page_text)
        all_text += page_text
        
        # Get all images on the page
        images = page.get_images()
        
        # Extract each image with size information
        for img_index, img in enumerate(images):
            try:
                xref = img[0]
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Handle images with masks
                pil_image = Image.open(io.BytesIO(image_bytes))
                
                # Check if there's a soft mask
                if "smask" in base_image and base_image["smask"]:
                    mask_image = pdf_document.extract_image(base_image["smask"])
                    mask = Image.open(io.BytesIO(mask_image["image"])).convert("L")
                    pil_image.putalpha(mask)
                
                # Convert CMYK to RGB if needed
                if pil_image.mode == "CMYK":
                    pil_image = pil_image.convert("RGB")
                
                # Get image dimensions
                width, height, pixel_area = get_image_dimensions(pil_image)
                
                # Classify image type
                classification = classify_image(pil_image, width, height, pixel_area)
                
                # Convert to base64
                buffered = io.BytesIO()
                pil_image.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                
                images_data.append({
                    "page": page_num + 1,
                    "index": img_index + 1,
                    "format": "png",
                    "base64": img_base64,
                    "width": width,
                    "height": height,
                    "pixel_area": pixel_area,
                    "type": classification["type"],
                    "aspect_ratio": classification["aspect_ratio"],
                    "confidence": classification["confidence"]
                })
                
            except Exception as e:
                # Fallback to raw image data
                try:
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height, pixel_area = get_image_dimensions(pil_image)
                    
                    img_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    images_data.append({
                        "page": page_num + 1,
                        "index": img_index + 1,
                        "format": image_ext,
                        "base64": img_base64,
                        "width": width,
                        "height": height,
                        "pixel_area": pixel_area,
                        "type": "unknown",
                        "confidence": "Low"
                    })
                except:
                    pass
    
    pdf_document.close()
    
    # Sort: photos first (by size descending), then signatures
    images_data.sort(key=lambda x: (x['type'] != 'photo', -x['pixel_area']))
    
    # Remove pixel_area from final output
    images_base64 = [{k: v for k, v in img.items() if k not in ['pixel_area']} for img in images_data]
    
    return images_base64, all_text


@app.route('/extract-nid', methods=['POST'])
def extract_nid():
    """API endpoint to extract NID data from PDF."""
    
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                "success": False,
                "error": "No file provided"
            }), 400
        
        file = request.files['file']
        
        # Check if file is PDF
        if not file.filename.endswith('.pdf'):
            return jsonify({
                "success": False,
                "error": "File must be a PDF"
            }), 400
        
        # Read PDF bytes
        pdf_bytes = file.read()
        
        # Extract images and text
        images, text = extract_images_and_text_from_pdf(pdf_bytes)
        
        # Print extracted text for debugging
        print("\n=== Extracted Text from PDF ===")
        print(text)
        print("==============================\n")
        
        # Parse NID data
        parsed_data = parse_nid_text(text)
        
        # Return response
        return jsonify({
            "success": True,
            "data": parsed_data,
            "images": images
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/extract-transparent', methods=['POST'])
def extract_transparent():
    """API endpoint to extract NID data with transparent background images."""
    
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                "success": False,
                "error": "No file provided"
            }), 400
        
        file = request.files['file']
        
        # Check if file is PDF
        if not file.filename.endswith('.pdf'):
            return jsonify({
                "success": False,
                "error": "File must be a PDF"
            }), 400
        
        # Read PDF bytes
        pdf_bytes = file.read()
        
        # Extract images and text
        images, text = extract_images_and_text_from_pdf(pdf_bytes)
        
        # Print extracted text for debugging
        print("\n=== Extracted Text from PDF ===")
        print(text)
        print("==============================\n")
        
        # Parse NID data
        parsed_data = parse_nid_text(text)
        
        # Process images for background removal
        transparent_images = []
        
        # Images are already sorted by size (largest first)
        # Process largest image (photo) first
        if len(images) > 0:
            print(f"Processing image 1 (size: {images[0]['width']}x{images[0]['height']}) as profile photo...")
            profile_bg_removed = remove_background(images[0]['base64'])
            if profile_bg_removed:
                transparent_images.append({
                    "page": images[0]['page'],
                    "index": 0,
                    "format": "png",
                    "base64": profile_bg_removed,
                    "label": "Profile (No Background)",
                    "width": images[0]['width'],
                    "height": images[0]['height']
                })
        
        # Process second image (signature) if it exists
        if len(images) > 1:
            print(f"Processing image 2 (size: {images[1]['width']}x{images[1]['height']}) as signature...")
            try:
                signature_bg_removed = remove_background(images[1]['base64'])
                if signature_bg_removed:
                    transparent_images.append({
                        "page": images[1]['page'],
                        "index": 1,
                        "format": "png",
                        "base64": signature_bg_removed,
                        "label": "Signature (No Background)",
                        "width": images[1]['width'],
                        "height": images[1]['height']
                    })
                else:
                    print("Signature background removal returned None")
            except Exception as e:
                print(f"Error processing signature: {str(e)}")
        
        # Return response
        return jsonify({
            "success": True,
            "data": parsed_data,
            "images": images,
            "transparentImages": transparent_images
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

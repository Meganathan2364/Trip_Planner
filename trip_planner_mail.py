import streamlit as st
import os
import re
from groq import Groq
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import date, datetime, timedelta
from fpdf import FPDF
import requests
import json
import time

# --- Page Configuration ---
st.set_page_config(
    page_title="AI Trip Planner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS Styling ---
st.markdown("""
<style>
    .main-header { text-align: center; padding: 2rem 0; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 10px; margin-bottom: 2rem; }
    .section-header { background-color: #667eea; color: white; padding: 1rem; border-radius: 5px; margin: 2rem 0 1rem 0; font-weight: bold; }
    .section-header h3 { color: white !important; margin: 0; font-size: 1.2rem; }
    .trip-plan { background-color: #f8f9fa; padding: 2rem; border-radius: 10px; border-left: 5px solid #667eea; }
    .success-message { background-color: #d4edda; padding: 1rem; border-radius: 8px; border-left: 4px solid #28a745; margin: 1rem 0; }
</style>
""", unsafe_allow_html=True)

class WebSearcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TripPlannerApp/1.0 (Educational Use)'
        })
    
    def duckduckgo_search(self, query):
        """DuckDuckGo Instant Answer API - Free & Legal"""
        try:
            url = "https://api.duckduckgo.com/"
            params = {
                'q': f"{query} travel price cost",
                'format': 'json',
                'no_redirect': '1',
                'no_html': '1',
                'skip_disambig': '1'
            }
            
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    'abstract': data.get('AbstractText', ''),
                    'answer': data.get('Answer', ''),
                    'topics': [topic.get('Text', '') for topic in data.get('RelatedTopics', [])[:3]]
                }
        except Exception:
            pass
        return None
    
    def wikipedia_search(self, destination):
        """Wikipedia API - Free & Legal"""
        try:
            search_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
            destination_clean = destination.replace(' ', '_')
            
            response = self.session.get(f"{search_url}{destination_clean}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    'title': data.get('title', ''),
                    'extract': data.get('extract', ''),
                    'coordinates': data.get('coordinates', {}),
                    'page_url': data.get('content_urls', {}).get('desktop', {}).get('page', '')
                }
        except Exception:
            pass
        return None
    
    def openstreetmap_search(self, location):
        """OpenStreetMap Nominatim API - Free & Legal"""
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': f"{location}, India",
                'format': 'json',
                'limit': 1,
                'addressdetails': 1
            }
            
            headers = {'User-Agent': 'TripPlannerApp/1.0 (Educational)'}
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data:
                    return {
                        'display_name': data[0].get('display_name', ''),
                        'latitude': float(data[0].get('lat', 0)),
                        'longitude': float(data[0].get('lon', 0)),
                        'address': data[0].get('address', {})
                    }
        except Exception:
            pass
        return None
    
    def extract_prices_from_text(self, text):
        """Extract price information from text content"""
        if not text:
            return []
            
        rupee_patterns = [
            r'₹\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'rs\.?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'inr\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*rupees?',
            r'price[:\s]*₹?\s*(\d{1,3}(?:,\d{3})*)',
            r'cost[:\s]*₹?\s*(\d{1,3}(?:,\d{3})*)',
            r'from\s*₹?\s*(\d{1,3}(?:,\d{3})*)',
            r'starting\s*₹?\s*(\d{1,3}(?:,\d{3})*)',
        ]
        
        prices = []
        text_lower = text.lower()
        
        for pattern in rupee_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                try:
                    clean_price = match.replace(',', '').replace('.00', '')
                    price = int(float(clean_price))
                    if 300 <= price <= 500000:  # Reasonable travel price range
                        prices.append(price)
                except ValueError:
                    continue
        
        return sorted(list(set(prices)))

class StructuredTripPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        
    def header(self):
        """Clean header for each page"""
        self.set_font('Arial', 'B', 16)
        self.set_text_color(70, 70, 70)
        self.cell(0, 15, 'AI Trip Planner', 0, 1, 'C')
        self.ln(5)
        
    def footer(self):
        """Simple footer with page number"""
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
        
    def clean_text_for_pdf(self, text):
        """Clean text for PDF generation with ASCII-safe characters"""
        if not text:
            return ""
            
        text = str(text)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        
        replacements = {
            '₹': 'Rs.',
            '•': '-',
            '‑': '-',
            '–': '-',
            '—': '-',
            ''': "'",
            ''': "'",
            '"': '"',
            '"': '"',
            '…': '...',
            '°': ' degrees',
            '×': 'x',
            '÷': '/',
            'é': 'e',
            'è': 'e',
            'ê': 'e',
            'ë': 'e',
            'à': 'a',
            'á': 'a',
            'â': 'a',
            'ä': 'a',
            'ç': 'c',
            'ñ': 'n',
        }
        
        for unicode_char, ascii_replacement in replacements.items():
            text = text.replace(unicode_char, ascii_replacement)
            
        text = text.encode('ascii', 'ignore').decode('ascii')
        return text
        
    def add_title_section(self, destination, user_name, dates):
        """Create title section"""
        self.set_font('Arial', 'B', 24)
        self.set_text_color(0, 0, 0)
        self.cell(0, 15, f'Trip Plan to {self.clean_text_for_pdf(destination)}', 0, 1, 'C')
        self.ln(5)
        
        self.set_font('Arial', '', 12)
        self.cell(0, 8, f'For: {self.clean_text_for_pdf(user_name)}', 0, 1, 'C')
        self.cell(0, 8, f'Dates: {dates}', 0, 1, 'C')
        self.cell(0, 6, 'Personalized AI-Generated Itinerary', 0, 1, 'C')
        self.ln(10)
        
        self.set_font('Arial', 'B', 18)
        self.cell(0, 12, f'{self.clean_text_for_pdf(destination)} Trip Plan', 0, 1, 'L')
        self.ln(5)
    
    def add_section_header(self, title):
        """Add section header with underline"""
        self.ln(8)
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 0, 0)
        self.cell(0, 10, self.clean_text_for_pdf(title), 0, 1, 'L')
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)
    
    def add_paragraph(self, text):
        """Add paragraph text"""
        self.set_font('Arial', '', 11)
        self.set_text_color(0, 0, 0)
        clean_text = self.clean_text_for_pdf(text)
        self.multi_cell(0, 6, clean_text)
        self.ln(3)
    
    def add_bullet_point(self, text):
        """Add bullet point with ASCII-safe dash"""
        if not text or not text.strip():
            return
            
        self.set_font('Arial', '', 11)
        clean_text = self.clean_text_for_pdf(text)
        
        self.cell(10, 6, '-', 0, 0, 'L')
        remaining_width = self.w - self.l_margin - self.r_margin - 10
        
        x_pos = self.get_x()
        y_pos = self.get_y()
        
        self.multi_cell(remaining_width, 6, clean_text)
        self.ln(1)

    def add_detailed_day_by_day_itinerary(self, user_data):
        """Create detailed day-by-day itinerary with specific activities and costs"""
        
        self.add_section_header("📅 Day-by-Day Itinerary")
        
        # Get trip details
        try:
            duration = (user_data.get('return_date') - user_data.get('departure_date')).days + 1
            start_date = user_data.get('departure_date')
        except:
            duration = 7
            start_date = datetime.now().date()
        
        destination = user_data.get('destination', 'Delhi')
        interests = user_data.get('interests', ['History', 'Culture'])
        dietary_pref = user_data.get('dietary_pref', 'Non-Vegetarian')
        trip_type = user_data.get('trip_type', 'Friends')
        num_travelers = user_data.get('num_travelers', 5)
        
        # Define activity templates based on destination and interests
        activity_templates = self.get_activity_templates(destination, interests, dietary_pref, num_travelers)
        
        # Day 1 - Arrival Day
        day1_date = start_date.strftime('%Y-%m-%d')
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, f'Day 1 - {day1_date} - Arrival Day', 0, 1, 'L')
        self.ln(3)
        
        arrival_activities = [
            f"Morning: Arrive at {destination}'s Indira Gandhi International Airport (IGIA). Take a taxi or metro (Yellow Line) to the hotel.",
            f"Afternoon: Check-in at Hotel Orchid (Rs. 2,500/night), a budget-friendly option with amenities like a restaurant and 24-hour front desk. Explore nearby area.",
            "Evening: Enjoy a welcome dinner at the popular Karim's restaurant, serving delicious North Indian cuisine. (Rs. 500 per person)",
            f"Estimated daily cost for group: Rs. {4500 + (num_travelers * 500):,}"
        ]
        
        for activity in arrival_activities:
            self.add_bullet_point(activity)
        
        self.ln(8)
        
        # Main Exploration Days
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, f'Days 2-{duration-1} - Main Exploration', 0, 1, 'L')
        self.ln(3)
        
        # Generate detailed days 2 to duration-1
        for day_num in range(2, duration):
            current_date = (start_date + timedelta(days=day_num-1)).strftime('%Y-%m-%d')
            
            # Get activities for this day based on interests
            day_theme = self.get_day_theme(day_num, interests)
            activities = activity_templates.get(day_theme, activity_templates['default'])
            
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, f'Day {day_num}: {day_theme}', 0, 1, 'L')
            self.ln(2)
            
            # Morning activity
            morning_activity = activities['morning'].format(
                destination=destination,
                cost_per_person=activities['morning_cost'],
                total_cost=activities['morning_cost'] * num_travelers
            )
            self.add_bullet_point(f"Morning: {morning_activity}")
            
            # Afternoon activity
            afternoon_activity = activities['afternoon'].format(
                destination=destination,
                cost_per_person=activities.get('afternoon_cost', 0),
                total_cost=activities.get('afternoon_cost', 0) * num_travelers
            )
            self.add_bullet_point(f"Afternoon: {afternoon_activity}")
            
            # Evening activity
            evening_activity = activities['evening'].format(
                destination=destination,
                cost_per_person=activities['evening_cost'],
                total_cost=activities['evening_cost'] * num_travelers
            )
            self.add_bullet_point(f"Evening: {evening_activity}")
            
            # Daily cost estimate
            daily_cost = (activities['morning_cost'] + activities.get('afternoon_cost', 0) + 
                         activities['evening_cost'] + 1500) * num_travelers  # +1500 for meals/transport
            self.add_bullet_point(f"Estimated daily cost for group: Rs. {daily_cost:,}")
            
            self.ln(5)
        
        # Final Day - Departure
        if duration > 1:
            final_date = (start_date + timedelta(days=duration-1)).strftime('%Y-%m-%d')
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, f'Day {duration} - {final_date} - Departure Day', 0, 1, 'L')
            self.ln(2)
            
            departure_activities = [
                "Morning: Final shopping and souvenir collection. Visit local markets for last-minute purchases.",
                "Afternoon: Hotel checkout and departure preparations. Light lunch at hotel or nearby restaurant.",
                "Evening: Journey back home. Safe travels!"
            ]
            
            for activity in departure_activities:
                self.add_bullet_point(activity)
            
            self.ln(8)
    
    def get_day_theme(self, day_num, interests):
        """Get theme for each day based on interests"""
        themes = []
        
        if 'History' in interests:
            themes.append('Historical Exploration')
        if 'Nature' in interests:
            themes.append('Nature and Relaxation')
        if 'Food' in interests:
            themes.append('Culinary Adventure')
        if 'Culture' in interests:
            themes.append('Cultural Immersion')
        if 'Adventure' in interests:
            themes.append('Adventure Activities')
        if 'Shopping' in interests:
            themes.append('Shopping and Markets')
        
        # If no specific interests, use default themes
        if not themes:
            themes = ['City Exploration', 'Cultural Tour', 'Nature Walk']
        
        # Cycle through themes
        theme_index = (day_num - 2) % len(themes)
        return themes[theme_index]
    
    def get_activity_templates(self, destination, interests, dietary_pref, num_travelers):
        """Get detailed activity templates based on destination and preferences"""
        
        # Delhi-specific activities
        if destination.lower() == 'delhi':
            return {
                'Historical Exploration': {
                    'morning': 'Visit the magnificent Red Fort, a UNESCO World Heritage site with guided audio tour. (Rs. 200 per person)',
                    'morning_cost': 200,
                    'afternoon': 'Explore Jama Masjid and Chandni Chowk - try street kebabs, capture bustling lanes and traditional markets.',
                    'afternoon_cost': 150,
                    'evening': 'Sunset at Rooftop Cafe in Connaught Place with cocktails and live music. (Rs. 800 per person)',
                    'evening_cost': 800
                },
                'Nature and Relaxation': {
                    'morning': 'Visit the beautiful Akshardham Temple and enjoy the musical fountain show. (Rs. 150 per person)',
                    'morning_cost': 150,
                    'afternoon': 'Explore the serene Hauz Khas Village, known for its lakes, gardens, and shopping options.',
                    'afternoon_cost': 0,
                    'evening': 'Enjoy a relaxing sunset cruise on the Yamuna River. (Rs. 800 per person)',
                    'evening_cost': 800
                },
                'Culinary Adventure': {
                    'morning': 'Food walking tour of Old Delhi - taste parathas at Paranthe Wali Gali. (Rs. 300 per person)',
                    'morning_cost': 300,
                    'afternoon': 'Cooking class with local chef - learn to make traditional Delhi dishes. (Rs. 1200 per person)',
                    'afternoon_cost': 1200,
                    'evening': 'Dinner at famous Karim\'s restaurant - try their legendary mutton korma and kebabs. (Rs. 600 per person)',
                    'evening_cost': 600
                },
                'Cultural Immersion': {
                    'morning': 'Visit Humayun\'s Tomb, a UNESCO site and architectural marvel. (Rs. 40 per person)',
                    'morning_cost': 40,
                    'afternoon': 'Explore National Museum and Gandhi Smriti - rich Indian history and culture. (Rs. 100 per person)',
                    'afternoon_cost': 100,
                    'evening': 'Cultural performance at India Habitat Centre or local cultural center. (Rs. 500 per person)',
                    'evening_cost': 500
                },
                'Adventure Activities': {
                    'morning': 'Day-trip to Sanjay Van (Aravalli ridge) - guided trek and nature walk. Free entry, bring water and snacks.',
                    'morning_cost': 0,
                    'afternoon': 'Visit Garden of Five Senses for adventure activities and photography. (Rs. 30 per person)',
                    'afternoon_cost': 30,
                    'evening': 'Go-karting or paintball at local adventure parks. (Rs. 1000 per person)',
                    'evening_cost': 1000
                },
                'Shopping and Markets': {
                    'morning': 'Explore Dilli Haat - handicrafts, textiles, and souvenirs from all over India. (Rs. 50 entry)',
                    'morning_cost': 50,
                    'afternoon': 'Shopping at Connaught Place and Khan Market - books, clothes, and local items.',
                    'afternoon_cost': 0,
                    'evening': 'Street shopping at Sarojini Nagar Market - bargaining and local fashion finds.',
                    'evening_cost': 0
                },
                'default': {
                    'morning': 'City sightseeing tour covering major attractions and landmarks. (Rs. 300 per person)',
                    'morning_cost': 300,
                    'afternoon': 'Local market visit and cultural exploration with guide.',
                    'afternoon_cost': 200,
                    'evening': 'Traditional dinner and cultural show. (Rs. 700 per person)',
                    'evening_cost': 700
                }
            }
        
        # Generic templates for other destinations
        return {
            'Historical Exploration': {
                'morning': 'Visit historical monuments and heritage sites in {destination}. (Rs. {cost_per_person} per person)',
                'morning_cost': 200,
                'afternoon': 'Guided heritage walk and museum visits in old city areas.',
                'afternoon_cost': 150,
                'evening': 'Traditional dinner at heritage restaurant. (Rs. {cost_per_person} per person)',
                'evening_cost': 600
            },
            'Nature and Relaxation': {
                'morning': 'Nature walk in {destination} gardens and parks. (Rs. {cost_per_person} per person)',
                'morning_cost': 100,
                'afternoon': 'Relaxing time at botanical gardens or lakeside areas.',
                'afternoon_cost': 0,
                'evening': 'Sunset viewing at scenic location with refreshments. (Rs. {cost_per_person} per person)',
                'evening_cost': 400
            },
            'default': {
                'morning': 'City exploration and major attractions tour. (Rs. {cost_per_person} per person)',
                'morning_cost': 300,
                'afternoon': 'Local culture and market exploration.',
                'afternoon_cost': 200,
                'evening': 'Traditional dinner and entertainment. (Rs. {cost_per_person} per person)',
                'evening_cost': 700
            }
        }

    def add_enhanced_budget_breakdown(self, user_data):
        """Create a properly formatted budget breakdown table"""
        
        self.add_section_header("💰 Budget Breakdown")
        
        # Calculate budget allocations
        total_budget = user_data.get('total_budget', 200000)
        accommodation = int(total_budget * user_data.get('accommodation_pct', 40) / 100)
        transport = int(total_budget * user_data.get('transport_pct', 25) / 100)
        food = int(total_budget * user_data.get('food_pct', 20) / 100)
        activities = int(total_budget * user_data.get('activities_pct', 15) / 100)
        miscellaneous = total_budget - (accommodation + transport + food + activities)
        
        try:
            duration = (user_data.get('return_date') - user_data.get('departure_date')).days + 1
        except:
            duration = 7
        
        # Table data
        budget_data = [
            ['Transportation', f'Rs. {transport:,}', f'{", ".join(user_data.get("transport_mode", ["Flight"]))} + local transport'],
            ['Accommodation', f'Rs. {accommodation:,}', f'Hotels for {duration} nights'],
            ['Food & Dining', f'Rs. {food:,}', f'{user_data.get("dietary_pref", "Mixed")} cuisine preferences'],
            ['Activities', f'Rs. {activities:,}', 'Sightseeing and experiences'],
            ['Miscellaneous', f'Rs. {miscellaneous:,}', 'Shopping and emergency fund']
        ]
        
        # Create table
        headers = ['Category', 'Allocated Budget', 'Details']
        col_widths = [50, 40, 90]  # Custom column widths
        
        # Headers
        self.set_font('Arial', 'B', 11)
        self.set_fill_color(70, 130, 180)  # Steel blue
        self.set_text_color(255, 255, 255)  # White text
        
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 12, header, 1, 0, 'C', True)
        self.ln()
        
        # Data rows
        self.set_font('Arial', '', 10)
        self.set_text_color(0, 0, 0)  # Black text
        
        for row_idx, row in enumerate(budget_data):
            # Alternate row colors
            if row_idx % 2 == 0:
                self.set_fill_color(245, 245, 245)  # Light gray
            else:
                self.set_fill_color(255, 255, 255)  # White
                
            for i, cell in enumerate(row):
                clean_text = self.clean_text_for_pdf(str(cell))
                align = 'R' if 'Rs.' in clean_text else 'L'
                self.cell(col_widths[i], 10, clean_text, 1, 0, align, True)
            self.ln()
        
        # Total row
        self.set_font('Arial', 'B', 11)
        self.set_fill_color(70, 130, 180)
        self.set_text_color(255, 255, 255)
        
        total_row = ['TOTAL BUDGET', f'Rs. {total_budget:,}', 'Complete trip allocation']
        for i, cell in enumerate(total_row):
            clean_text = self.clean_text_for_pdf(str(cell))
            align = 'R' if 'Rs.' in clean_text else 'L'
            self.cell(col_widths[i], 12, clean_text, 1, 0, align, True)
        self.ln()
        
        self.ln(5)

    def add_comprehensive_accommodation_section(self, user_data):
        """Add detailed accommodation with specific hotel recommendations"""
        
        self.add_section_header("🏨 Where to Stay - Detailed Recommendations")
        
        destination = user_data.get('destination', 'Delhi')
        budget = user_data.get('total_budget', 50000)
        trip_type = user_data.get('trip_type', 'Friends')
        
        # Budget Hotels
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Budget Hotels (Rs. 1,500-3,000/night)', 0, 1, 'L')
        self.ln(2)
        
        budget_hotels = [
            f'Hotel Orchid {destination} - Clean rooms, 24-hour front desk, restaurant, WiFi (Rs. 2,500/night)',
            f'Backpacker Hostel - Shared facilities, common area, perfect for {trip_type.lower()} groups (Rs. 1,500/night)',
            f'Tourist Guest House - Basic amenities, central location, budget-friendly (Rs. 2,000/night)'
        ]
        
        for hotel in budget_hotels:
            self.add_bullet_point(hotel)
        
        self.ln(3)
        
        # Mid-range Hotels
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Mid-range Hotels (Rs. 3,000-6,000/night)', 0, 1, 'L')
        self.ln(2)
        
        midrange_hotels = [
            f'Hotel Metropolitan - 4-star comfort, gym, spa, multiple restaurants (Rs. 4,500/night)',
            f'Boutique Heritage Hotel - Local architecture, modern amenities, rooftop dining (Rs. 5,000/night)',
            f'Business Hotel Express - Perfect for comfort, conference rooms, executive services (Rs. 3,800/night)'
        ]
        
        for hotel in midrange_hotels:
            self.add_bullet_point(hotel)
        
        self.ln(3)
        
        # Premium Hotels
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Premium Hotels (Rs. 6,000+/night)', 0, 1, 'L')
        self.ln(2)
        
        premium_hotels = [
            f'The Grand Palace Hotel - 5-star luxury, full-service spa, fine dining, concierge (Rs. 8,500/night)',
            f'Heritage Mansion - Historic property, unique architecture, premium hospitality (Rs. 7,200/night)',
            f'Luxury Resort & Spa - Complete resort experience, recreational facilities, premium service (Rs. 9,000/night)'
        ]
        
        for hotel in premium_hotels:
            self.add_bullet_point(hotel)
        
        self.ln(5)

    def add_transportation_section(self, user_data):
        """Add transportation details"""
        
        self.add_section_header("🚗 Transportation Guide")
        
        departure_city = user_data.get('departure_city', 'Mumbai')
        destination = user_data.get('destination', 'Delhi')
        transport_modes = user_data.get('transport_mode', ['Flight'])
        
        # Main transportation
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Main Travel Options', 0, 1, 'L')
        self.ln(2)
        
        transport_details = {
            'Flight': f'{departure_city} to {destination} by air - fastest option, 2-3 hours journey time',
            'Train': f'{departure_city} to {destination} by train - comfortable, scenic journey, 8-12 hours',
            'Bus': f'{departure_city} to {destination} by bus - economical option, overnight journey',
            'Car Rental': f'{departure_city} to {destination} by car - flexible timing, road trip experience'
        }
        
        for mode in transport_modes:
            if mode in transport_details:
                self.add_bullet_point(transport_details[mode])
        
        self.ln(3)
        
        # Local transportation
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Local Transportation', 0, 1, 'L')
        self.ln(2)
        
        local_transport = [
            f'Metro system - efficient and economical city travel in {destination}',
            f'Taxi and ride-sharing - convenient door-to-door service, app-based booking',
            f'Auto-rickshaws - local experience, good for short distances',
            f'Local buses - budget-friendly option for city exploration'
        ]
        
        for transport in local_transport:
            self.add_bullet_point(transport)
        
        self.ln(5)

    def add_detailed_food_section(self, user_data):
        """Add comprehensive food section with specific restaurant recommendations"""
        
        self.add_section_header("🍽️ Food & Dining - Complete Guide")
        
        destination = user_data.get('destination', 'Delhi')
        dietary_pref = user_data.get('dietary_pref', 'Non-Vegetarian')
        
        # Must-try dishes section
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, f'Must-Try {destination} Specialties', 0, 1, 'L')
        self.ln(2)
        
        if destination.lower() == 'delhi':
            if dietary_pref == 'Non-Vegetarian':
                dishes = [
                    'Butter Chicken at Moti Mahal - birthplace of this famous dish (Rs. 400 per plate)',
                    'Kebabs at Karim\'s - legendary Jama Masjid restaurant, 100+ years old (Rs. 300-500 per plate)',
                    'Nihari at Al Jawahar - slow-cooked mutton stew, Old Delhi specialty (Rs. 350 per plate)',
                    'Biryani at Biryani Blues - aromatic rice with meat, modern presentation (Rs. 450 per plate)'
                ]
            elif dietary_pref == 'Vegetarian':
                dishes = [
                    'Chole Bhature at Sita Ram Diwan Chand - iconic Delhi breakfast (Rs. 100 per plate)',
                    'Parathas at Paranthe Wali Gali - stuffed bread varieties, century-old tradition (Rs. 80-120 per paratha)',
                    'Daulat Ki Chaat - winter delicacy, milk foam sweet (Rs. 50 per bowl)',
                    'Rajma Chawal at local dhabas - kidney beans with rice, comfort food (Rs. 150 per plate)'
                ]
            else:
                dishes = [
                    'Street Food Tour - gol gappa, aloo tikki, raj kachori (Rs. 200-300 total)',
                    'Traditional Thali - complete meal with variety of dishes (Rs. 300-500 per thali)',
                    'Local Sweets - gulab jamun, jalebi, kulfi (Rs. 50-100 per item)',
                    'Lassi and Chaas - traditional drinks, perfect with meals (Rs. 50-80 per glass)'
                ]
        else:
            # Generic recommendations for other destinations
            dishes = [
                f'Local specialty dishes of {destination} - regional flavors and traditional preparations',
                f'Street food specialties - popular local snacks and quick bites',
                f'Traditional restaurants - authentic regional cuisine and family recipes',
                f'Modern interpretations - contemporary takes on classic dishes'
            ]
        
        for dish in dishes:
            self.add_bullet_point(dish)
        
        self.ln(3)
        
        # Restaurant recommendations by budget
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Restaurant Recommendations by Budget', 0, 1, 'L')
        self.ln(2)
        
        restaurant_categories = [
            'Budget Dining (Rs. 200-500/meal) - Local dhabas, street food joints, casual eateries',
            'Mid-range Dining (Rs. 500-1500/meal) - Popular restaurants, cafe chains, themed restaurants',
            'Fine Dining (Rs. 1500+/meal) - Premium restaurants, hotel dining, specialty cuisine restaurants',
            'Food Courts & Quick Bites (Rs. 150-400/meal) - Mall food courts, fast food, snack counters'
        ]
        
        for category in restaurant_categories:
            self.add_bullet_point(category)
        
        self.ln(5)

    def add_comprehensive_packing_tips(self, user_data):
        """Add detailed packing tips based on destination, season, and activities"""
        
        self.add_section_header("🎒 Packing Essentials - Complete Checklist")
        
        destination = user_data.get('destination', 'Delhi')
        interests = user_data.get('interests', [])
        trip_type = user_data.get('trip_type', 'Friends')
        duration = 7
        
        try:
            duration = (user_data.get('return_date') - user_data.get('departure_date')).days + 1
            travel_month = user_data.get('departure_date').month
        except:
            travel_month = 9  # September
        
        # Basic Essentials
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Essential Documents & Money', 0, 1, 'L')
        self.ln(2)
        
        document_essentials = [
            'Valid photo ID (Aadhar Card, Passport, Driving License) - keep both original and copies',
            'Train/flight tickets and hotel booking confirmations - digital and printed copies',
            'Travel insurance documents and emergency contact details',
            'Medical prescriptions and health certificates if required',
            f'Cash in small denominations (Rs. 5,000-10,000) + ATM/credit cards',
            'Digital copies of all documents stored in cloud (Google Drive, Dropbox)'
        ]
        
        for item in document_essentials:
            self.add_bullet_point(item)
        
        self.ln(3)
        
        # Clothing Based on Season and Duration
        self.set_font('Arial', 'B', 12)
        season = self.get_season_info(travel_month, destination)
        self.cell(0, 8, f'Clothing for {season["name"]} in {destination}', 0, 1, 'L')
        self.ln(2)
        
        clothing_items = [
            f'Comfortable walking shoes (2 pairs) - broken-in sneakers and formal shoes',
            f'Weather-appropriate clothing - {season["clothing_advice"]}',
            f'Undergarments for {duration + 2} days - pack extra for comfort',
            f'Sleepwear and comfortable lounging clothes',
            f'One formal outfit for fine dining or cultural events',
            'Quick-dry socks and comfortable underwear',
            f'Weather protection - {season["weather_gear"]}'
        ]
        
        for item in clothing_items:
            self.add_bullet_point(item)
        
        self.ln(3)
        
        # Electronics and Gadgets
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Electronics & Gadgets', 0, 1, 'L')
        self.ln(2)
        
        electronics = [
            'Smartphone with offline maps downloaded (Google Maps offline)',
            'Power bank (10,000-20,000 mAh) and charging cables',
            'Universal power adapter and portable charger',
            'Camera with extra memory cards and batteries',
            'Earphones/headphones for travel entertainment',
            'Portable WiFi hotspot or local SIM card information'
        ]
        
        # Add interest-specific electronics
        if 'Photography' in interests:
            electronics.extend([
                'DSLR/mirrorless camera with multiple lenses',
                'Tripod (compact travel tripod)',
                'Camera cleaning kit and lens filters'
            ])
        
        if 'Adventure' in interests:
            electronics.extend([
                'Action camera (GoPro) with mounts and accessories',
                'GPS device or GPS watch for trekking'
            ])
        
        for item in electronics:
            self.add_bullet_point(item)
        
        self.ln(3)
        
        # Health and Personal Care
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Health & Personal Care', 0, 1, 'L')
        self.ln(2)
        
        health_items = [
            'Basic first-aid kit - band-aids, antiseptic, pain relievers',
            'Personal medications with extra supply',
            'Hand sanitizer and wet wipes',
            'Sunscreen (SPF 30+) and after-sun lotion',
            'Insect repellent (especially for outdoor activities)',
            'Personal toiletries in travel-size containers',
            'Oral rehydration salts (ORS) and digestive aids',
            'Face masks and any required COVID-19 related items'
        ]
        
        for item in health_items:
            self.add_bullet_point(item)
        
        self.ln(3)
        
        # Interest-Specific Packing
        if interests:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, f'Special Items for Your Interests', 0, 1, 'L')
            self.ln(2)
            
            interest_items = []
            
            if 'Adventure' in interests:
                interest_items.extend([
                    'Trekking shoes and hiking socks',
                    'Quick-dry adventure clothing and cargo pants',
                    'Waterproof backpack and dry bags',
                    'Water bottles and energy bars'
                ])
            
            if 'Culture' in interests:
                interest_items.extend([
                    'Modest clothing for religious sites (covered shoulders/legs)',
                    'Comfortable shoes for walking in museums',
                    'Notebook for cultural observations'
                ])
            
            if 'Food' in interests:
                interest_items.extend([
                    'Digestive tablets and probiotics',
                    'Food diary or camera for food photography',
                    'Reusable water bottle for food tours'
                ])
            
            if 'Shopping' in interests:
                interest_items.extend([
                    'Extra luggage space or foldable duffel bag',
                    'Calculator for currency conversion',
                    'Measuring tape for clothing purchases'
                ])
            
            if 'Nature' in interests:
                interest_items.extend([
                    'Binoculars for bird watching',
                    'Field notebook for nature observations',
                    'Comfortable outdoor seating (portable chair)'
                ])
            
            for item in interest_items:
                self.add_bullet_point(item)
        
        self.ln(3)
        
        # Miscellaneous but Important
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Miscellaneous Essentials', 0, 1, 'L')
        self.ln(2)
        
        misc_items = [
            'Reusable water bottle and snacks for travel',
            'Travel pillow and eye mask for comfortable journey',
            'Laundry bag and travel-size detergent',
            'Swiss Army knife or multi-tool (pack in checked luggage)',
            'Duct tape and zip ties for emergency repairs',
            'Travel locks for luggage security',
            'Emergency whistle and flashlight',
            f'Local guidebook or phrasebook for {destination}'
        ]
        
        for item in misc_items:
            self.add_bullet_point(item)
        
        self.ln(5)
    
    def get_season_info(self, month, destination):
        """Get seasonal information for packing advice"""
        
        if destination.lower() == 'delhi':
            if month in [12, 1, 2]:  # Winter
                return {
                    'name': 'Winter',
                    'clothing_advice': 'warm layers, sweaters, jacket, long pants, warm socks',
                    'weather_gear': 'light jacket, scarf, and gloves for evening'
                }
            elif month in [3, 4, 5]:  # Spring/Hot
                return {
                    'name': 'Hot Season',
                    'clothing_advice': 'light cotton clothing, breathable fabrics, shorts, t-shirts',
                    'weather_gear': 'wide-brimmed hat, sunglasses, and light scarf'
                }
            elif month in [6, 7, 8, 9]:  # Monsoon
                return {
                    'name': 'Monsoon Season',
                    'clothing_advice': 'quick-dry clothes, light rain jacket, waterproof shoes',
                    'weather_gear': 'umbrella, waterproof bag covers, and rain poncho'
                }
            else:  # Post-monsoon
                return {
                    'name': 'Pleasant Weather',
                    'clothing_advice': 'comfortable cotton clothes, light layers for evening',
                    'weather_gear': 'light sweater for evening and early morning'
                }
        
        # Generic advice for other destinations
        return {
            'name': 'General Season',
            'clothing_advice': 'comfortable clothing suitable for the local climate',
            'weather_gear': 'umbrella and light jacket for weather changes'
        }

    def add_comprehensive_local_tips(self, user_data):
        """Add detailed local tips for the destination"""
        
        self.add_section_header("🌍 Local Tips & Cultural Guidelines")
        
        destination = user_data.get('destination', 'Delhi')
        trip_type = user_data.get('trip_type', 'Friends')
        interests = user_data.get('interests', [])
        
        # Cultural Etiquette
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Cultural Etiquette & Customs', 0, 1, 'L')
        self.ln(2)
        
        if destination.lower() == 'delhi':
            cultural_tips = [
                'Remove shoes when entering temples, gurdwaras, and some traditional homes',
                'Dress modestly at religious sites - cover shoulders, arms, and legs',
                'Use "Namaste" greeting with palms together - respectful and appreciated',
                'Avoid pointing feet toward people or religious objects',
                'Use right hand for eating, greeting, and giving/receiving items',
                'Photography may be restricted in some religious and government buildings',
                'Respect local customs during festivals and religious ceremonies'
            ]
        else:
            cultural_tips = [
                f'Research {destination} cultural customs and local etiquette before arrival',
                'Dress appropriately according to local customs and religious sites',
                'Learn basic local greetings and common phrases',
                'Respect religious and cultural practices',
                'Be mindful of photography restrictions at cultural sites',
                'Follow local dining etiquette and customs'
            ]
        
        for tip in cultural_tips:
            self.add_bullet_point(tip)
        
        self.ln(3)
        
        # Money and Bargaining
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Money Matters & Bargaining', 0, 1, 'L')
        self.ln(2)
        
        money_tips = [
            'Carry small denominations (Rs. 10, 20, 50, 100) for street vendors and auto-rickshaws',
            'Bargaining is expected at local markets - start at 30-40% of quoted price',
            'Fixed price shops and malls don\'t allow bargaining - prices are set',
            'Keep money in multiple places - wallet, bag, and hidden pocket',
            'ATMs are widely available - use bank ATMs for better security',
            'Digital payments (Paytm, Google Pay, PhonePe) are widely accepted',
            'Tipping: 10% at restaurants, Rs. 20-50 for hotel staff, Rs. 10-20 for taxi drivers'
        ]
        
        for tip in money_tips:
            self.add_bullet_point(tip)
        
        self.ln(3)
        
        # Transportation Tips
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Getting Around Like a Local', 0, 1, 'L')
        self.ln(2)
        
        if destination.lower() == 'delhi':
            transport_tips = [
                'Delhi Metro is the fastest way to travel - buy a metro card for convenience',
                'Use Ola/Uber for comfortable rides - safer than negotiating with taxi drivers',
                'Auto-rickshaws should use the meter - insist on it or agree on fare beforehand',
                'Avoid rush hours (8-10 AM, 6-8 PM) for smoother travel',
                'Download offline maps - Delhi traffic can be unpredictable',
                'Bus routes are extensive but can be crowded - metro is more comfortable',
                'Keep traffic conditions in mind - allow extra time for important appointments'
            ]
        else:
            transport_tips = [
                f'Research {destination} public transportation options before arrival',
                'Use ride-sharing apps for safe and convenient travel',
                'Negotiate taxi fares in advance or insist on using the meter',
                'Download offline maps and transportation apps',
                'Keep local transportation schedules and routes handy',
                'Allow extra time for travel during peak hours'
            ]
        
        for tip in transport_tips:
            self.add_bullet_point(tip)
        
        self.ln(3)
        
        # Food and Water Safety
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Food & Water Safety', 0, 1, 'L')
        self.ln(2)
        
        food_safety_tips = [
            'Drink bottled water or properly boiled water - avoid tap water',
            'Eat at busy restaurants with high turnover - fresher food',
            'Avoid raw salads and unpeeled fruits from street vendors',
            'Street food is generally safe at popular, crowded stalls',
            'Carry ORS packets and basic stomach medications',
            'Wash hands frequently or use hand sanitizer before eating',
            'Start with milder spices and gradually try spicier food'
        ]
        
        for tip in food_safety_tips:
            self.add_bullet_point(tip)
        
        self.ln(3)
        
        # Safety and Security
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Safety & Security Guidelines', 0, 1, 'L')
        self.ln(2)
        
        safety_tips = [
            'Keep copies of important documents separate from originals',
            'Avoid displaying expensive jewelry, cameras, or large amounts of cash',
            'Stay in groups, especially in crowded markets and tourist areas',
            'Be cautious of overly friendly strangers offering help or deals',
            'Keep hotel address and contact number written down in local language',
            'Trust your instincts - if something feels wrong, remove yourself from the situation',
            'Use hotel safes for valuable items and important documents',
            'Keep emergency numbers saved in your phone and written down'
        ]
        
        for tip in safety_tips:
            self.add_bullet_point(tip)
        
        self.ln(3)
        
        # Communication Tips
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Communication & Language', 0, 1, 'L')
        self.ln(2)
        
        communication_tips = [
            'English is widely spoken in tourist areas and hotels',
            'Learn basic local phrases: "Thank you" (Dhanyawad), "How much?" (Kitna?)',
            'Download Google Translate app with offline language packs',
            'Keep hotel business card with address in local language',
            'Use translation apps for menu reading and basic communication',
            'Locals are generally helpful - don\'t hesitate to ask for directions',
            'Speak clearly and be patient - language barriers are manageable'
        ]
        
        for tip in communication_tips:
            self.add_bullet_point(tip)
        
        self.ln(3)
        
        # Interest-Specific Local Tips
        if interests:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'Tips for Your Specific Interests', 0, 1, 'L')
            self.ln(2)
            
            interest_tips = []
            
            if 'Photography' in interests:
                interest_tips.extend([
                    'Ask permission before photographing people, especially in rural areas',
                    'Golden hour photography is best - early morning and late afternoon',
                    'Protect camera equipment from dust and humidity'
                ])
            
            if 'Food' in interests:
                interest_tips.extend([
                    'Visit local markets in the morning for fresh ingredients',
                    'Ask hotel staff for authentic local restaurant recommendations',
                    'Try regional breakfast dishes - often the most authentic meals'
                ])
            
            if 'Shopping' in interests:
                interest_tips.extend([
                    'Government emporiums have fixed prices and authentic products',
                    'Best bargains are found in local markets, not tourist areas',
                    'Check weight restrictions for flights before buying heavy items'
                ])
            
            if 'Adventure' in interests:
                interest_tips.extend([
                    'Book adventure activities through reputable tour operators',
                    'Check weather conditions before outdoor activities',
                    'Inform hotel staff about your adventure plans and expected return'
                ])
            
            if 'Culture' in interests:
                interest_tips.extend([
                    'Visit cultural sites early morning to avoid crowds',
                    'Hire local guides for deeper cultural insights',
                    'Attend local festivals or cultural events if timing aligns'
                ])
            
            for tip in interest_tips:
                self.add_bullet_point(tip)
        
        self.ln(5)
    
    def add_emergency_contacts_section(self, user_data):
        """Add emergency contacts and important information"""
        
        self.add_section_header("🚨 Emergency Contacts & Important Information")
        
        # Personal contacts
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Personal Emergency Contacts', 0, 1, 'L')
        self.ln(2)
        
        contacts = [
            f"Primary Traveler: {user_data.get('name', 'Not provided')} - {user_data.get('mobile', 'Not provided')}",
            f"Emergency Contact: {user_data.get('emergency_contact', 'Not provided')}"
        ]
        
        for contact in contacts:
            self.add_bullet_point(contact)
        
        self.ln(3)
        
        # Official emergency numbers
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Official Emergency Numbers (India)', 0, 1, 'L')
        self.ln(2)
        
        emergency_numbers = [
            'Universal Emergency: 112 (Police, Fire, Medical)',
            'Police: 100',
            'Fire Brigade: 101',
            'Ambulance: 108',
            'Tourist Helpline: 1363 (24x7 multilingual support)',
            'Women\'s Safety: 1091',
            'Railway Enquiry: 139',
            'Road Accident Emergency: 1073'
        ]
        
        for number in emergency_numbers:
            self.add_bullet_point(number)
        
        self.ln(3)
        
        # Important Services
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'Important Services & Contacts', 0, 1, 'L')
        self.ln(2)
        
        services = [
            'Airport Enquiry: Check specific airport contact numbers',
            'Indian Railways: 139 (booking and enquiry)',
            'Taxi/Cab Services: Ola (Dial Ola), Uber (app-based)',
            'Medical Emergency: Nearest hospital contact numbers',
            'Embassy/Consulate: Keep relevant contact if international traveler',
            'Travel Insurance: Keep policy number and emergency contact handy'
        ]
        
        for service in services:
            self.add_bullet_point(service)
        
        self.ln(5)

    def create_structured_pdf(self, trip_plan: str, user_data: dict) -> bytes:
        """Create comprehensive PDF with all detailed sections"""
        
        pdf = StructuredTripPDF()
        pdf.add_page()
        
        # Title section
        destination = user_data.get('destination', 'Your Destination')
        user_name = user_data.get('name', 'Traveler')
        start_date = str(user_data.get('departure_date', 'N/A'))
        end_date = str(user_data.get('return_date', 'N/A'))
        dates = f"{start_date} to {end_date}"
        
        pdf.add_title_section(destination, user_name, dates)
        
        # Add overview section
        try:
            duration = (user_data.get('return_date') - user_data.get('departure_date')).days + 1
        except:
            duration = 7
            
        overview_text = f"""This {duration}-day {user_data.get('trip_type', 'adventure').lower()} trip to {destination} is designed for {user_data.get('num_travelers', 2)} travelers with a total budget of Rs. {user_data.get('total_budget', 50000):,}.

The itinerary focuses on {', '.join(user_data.get('interests', ['sightseeing'])[:3]).lower()} with a {user_data.get('travel_pace', 'moderate').lower()}-paced schedule, featuring {user_data.get('dietary_pref', 'diverse')} dining options and {', '.join(user_data.get('transport_mode', ['mixed']))} transportation."""
        
        pdf.add_section_header("📋 Trip Overview")
        pdf.add_paragraph(overview_text)
        
        # Add all detailed sections
        pdf.add_detailed_day_by_day_itinerary(user_data)
        pdf.add_enhanced_budget_breakdown(user_data)
        pdf.add_comprehensive_accommodation_section(user_data)
        pdf.add_transportation_section(user_data)
        pdf.add_detailed_food_section(user_data)
        pdf.add_comprehensive_packing_tips(user_data)
        pdf.add_comprehensive_local_tips(user_data)
        pdf.add_emergency_contacts_section(user_data)
        
        # Add closing note
        pdf.ln(10)
        pdf.set_font('Arial', 'I', 11)
        pdf.set_text_color(100, 100, 100)
        final_note = f"Enjoy your {duration}-day adventure in {destination}! This personalized itinerary matches your interests and budget. Have a wonderful and safe trip!"
        pdf.multi_cell(0, 6, pdf.clean_text_for_pdf(final_note))
        
        return pdf.output(dest='S')

class AITripPlanner:
    def __init__(self):
        """Initialize the AI Trip Planner."""
        self.groq_client = None
        self.web_searcher = WebSearcher()
        self.initialize_groq()
        
    def initialize_groq(self):
        """Initialize the Groq client from Streamlit secrets."""
        try:
            groq_api_key = st.secrets.get("GROQ_API_KEY")
            if groq_api_key:
                self.groq_client = Groq(api_key=groq_api_key)
            else:
                st.error("⚠️ AI service not configured. Please contact administrator.")
        except Exception as e:
            st.error(f"⚠️ Error initializing AI service: {str(e)}")

    def create_structured_pdf(self, trip_plan: str, user_data: dict) -> bytes:
        """Create a beautifully structured PDF with comprehensive information"""
        
        pdf = StructuredTripPDF()
        return pdf.create_structured_pdf(trip_plan, user_data)

    def send_email(self, user_email: str, user_name: str, trip_plan: str, user_data: dict) -> bool:
        """Send the trip plan as a PDF attachment."""
        try:
            sender_email = st.secrets.get("SENDER_EMAIL")
            sender_password = st.secrets.get("SENDER_PASSWORD")
            if not sender_email or not sender_password:
                st.error("⚠️ Email service not configured. Please contact administrator.")
                return False

            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = user_email
            msg['Subject'] = f"Your Personalized Trip Plan for {user_data.get('destination', 'your destination')}"
            
            try:
                duration = (user_data.get('return_date') - user_data.get('departure_date')).days + 1
            except:
                duration = 7
            
            html_body = f"""
            <html>
            <body>
                <h2 style="color: #667eea;">Dear {user_name},</h2>
                <p>Your personalized trip plan is ready! We've created a detailed itinerary based on your preferences and current travel information.</p>
                
                <h3>Trip Summary:</h3>
                <ul>
                    <li><strong>Destination:</strong> {user_data.get('destination', 'N/A')}</li>
                    <li><strong>Duration:</strong> {duration} days</li>
                    <li><strong>Budget:</strong> Rs. {user_data.get('total_budget', 0):,}</li>
                    <li><strong>Transport:</strong> {', '.join(user_data.get('transport_mode', ['Flight']))}</li>
                    <li><strong>Interests:</strong> {', '.join(user_data.get('interests', ['General']))}</li>
                    <li><strong>Travel Style:</strong> {user_data.get('trip_type', 'Adventure')} trip with {user_data.get('travel_pace', 'moderate')} pace</li>
                </ul>
                
                <p style="color: #28a745;"><strong>✨ Enhanced with real-time travel data and current pricing!</strong></p>
                <p style="color: #667eea;"><strong>Have an amazing trip!</strong></p>
                
                <p style="font-size: 12px; color: #666;">Best regards,<br>AI Trip Planner Team</p>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_body, 'html'))
            
            pdf_bytes = self.create_structured_pdf(trip_plan, user_data)
            if not pdf_bytes:
                st.error("❌ PDF generation failed. Email not sent.")
                return False

            part = MIMEBase('application', 'octet-stream')
            part.set_payload(pdf_bytes)
            encoders.encode_base64(part)
            filename = f"Trip_Plan_{user_data.get('destination', 'trip').replace(' ', '_')}.pdf"
            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            msg.attach(part)

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
            return True
        except Exception as e:
            st.error(f"❌ Failed to send email: {str(e)}")
            return False

    def gather_travel_data(self, user_data):
        """Gather travel data from various sources"""
        travel_data = {
            'destination_info': {},
            'accommodation_data': {},
            'transportation_data': {},
            'local_info': {},
            'pricing_info': []
        }
        
        # Get destination information from Wikipedia
        wiki_data = self.web_searcher.wikipedia_search(user_data['destination'])
        if wiki_data:
            travel_data['destination_info'] = wiki_data
        
        # Get location coordinates
        location_data = self.web_searcher.openstreetmap_search(user_data['destination'])
        if location_data:
            travel_data['local_info']['coordinates'] = location_data
        
        # Search accommodation information
        hotel_query = f"{user_data['destination']} hotels accommodation price"
        ddg_hotels = self.web_searcher.duckduckgo_search(hotel_query)
        if ddg_hotels:
            all_text = f"{ddg_hotels.get('abstract', '')} {ddg_hotels.get('answer', '')} {' '.join(ddg_hotels.get('topics', []))}"
            prices = self.web_searcher.extract_prices_from_text(all_text)
            
            travel_data['accommodation_data'] = {
                'info': ddg_hotels,
                'prices_found': prices,
                'price_range': f"Rs. {min(prices):,} - Rs. {max(prices):,}" if prices else "Current pricing available"
            }
        
        # Search transportation information
        transport_query = f"{user_data['departure_city']} to {user_data['destination']} flight train bus price"
        ddg_transport = self.web_searcher.duckduckgo_search(transport_query)
        if ddg_transport:
            all_text = f"{ddg_transport.get('abstract', '')} {ddg_transport.get('answer', '')} {' '.join(ddg_transport.get('topics', []))}"
            prices = self.web_searcher.extract_prices_from_text(all_text)
            
            travel_data['transportation_data'] = {
                'info': ddg_transport,
                'prices_found': prices,
                'price_range': f"Rs. {min(prices):,} - Rs. {max(prices):,}" if prices else "Current pricing available"
            }
        
        return travel_data

    def collect_user_inputs(self) -> dict:
        """Display UI to collect user inputs."""
        st.markdown('<div class="main-header"><h1>🌍 AI Trip Planner</h1><p>Create your perfect personalized travel itinerary with real-time data</p></div>', unsafe_allow_html=True)
        
        user_data = {}

        st.markdown('<div class="section-header"><h3>📋 Personal Information</h3></div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            user_data['name'] = st.text_input("Full Name*", placeholder="Enter your full name")
            user_data['email'] = st.text_input("Email Address*", placeholder="your.email@example.com")
            user_data['age'] = st.number_input("Age", min_value=1, max_value=120, value=30)
        with col2:
            user_data['mobile'] = st.text_input("Mobile Number*", placeholder="+91 9876543210")
            user_data['emergency_contact'] = st.text_input("Emergency Contact", placeholder="Name: +91 9876543210")

        st.markdown('<div class="section-header"><h3>✈️ Trip Details</h3></div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            user_data['departure_city'] = st.text_input("Departure City*", placeholder="Mumbai")
            user_data['destination'] = st.text_input("Destination*", placeholder="Goa")
        with col2:
            user_data['departure_date'] = st.date_input("Departure Date*", min_value=date.today())
            user_data['return_date'] = st.date_input("Return Date*", min_value=date.today())
        with col3:
            user_data['num_travelers'] = st.number_input("Number of Travelers*", min_value=1, value=2)
            user_data['trip_type'] = st.selectbox("Trip Type", ["Family", "Couple", "Solo", "Friends", "Business"])

        st.markdown('<div class="section-header"><h3>💰 Budget Information</h3></div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            user_data['total_budget'] = st.number_input("Total Budget (INR)*", min_value=1000, step=5000, value=50000)
            user_data['budget_category'] = st.selectbox("Budget Category", ["Budget (Rs.5K-25K)", "Mid-Range (Rs.25K-75K)", "Luxury (Rs.75K+)"])
        with col2:
            st.write("**Budget Allocation**")
            user_data['accommodation_pct'] = st.slider("Accommodation %", 0, 100, 40)
            user_data['transport_pct'] = st.slider("Transportation %", 0, 100, 25)
            user_data['food_pct'] = st.slider("Food & Dining %", 0, 100, 20)
            user_data['activities_pct'] = st.slider("Activities %", 0, 100, 15)

        st.markdown('<div class="section-header"><h3>🚗 Travel Preferences</h3></div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            user_data['transport_mode'] = st.multiselect("Preferred Transportation*", ["Flight", "Train", "Bus", "Car Rental"], default=["Flight"])
            user_data['accommodation_type'] = st.multiselect("Accommodation Type", ["Hotels", "Resorts", "Homestays", "Hostels"], default=["Hotels"])
        with col2:
            user_data['travel_pace'] = st.selectbox("Travel Pace", ["Relaxed", "Moderate", "Fast-paced"])
            user_data['planning_style'] = st.selectbox("Planning Style", ["Highly Structured", "Flexible", "Spontaneous"])

        st.markdown('<div class="section-header"><h3>🎯 Interests & Requirements</h3></div>', unsafe_allow_html=True)
        interests_opts = ["Adventure", "Culture", "Nature", "Food", "Shopping", "Nightlife", "Relaxation", "History", "Beaches", "Photography"]
        user_data['interests'] = st.multiselect("Select Your Interests", interests_opts, default=["Culture", "Food", "Beaches"])
        
        col1, col2 = st.columns(2)
        with col1:
            user_data['dietary_pref'] = st.selectbox("Dietary Preference", ["Vegetarian", "Non-Vegetarian", "Vegan", "No Preference"])
            user_data['food_allergies'] = st.text_input("Food Allergies", placeholder="e.g., Peanuts, Gluten")
        with col2:
            user_data['accessibility_needs'] = st.text_input("Accessibility Needs", placeholder="e.g., Wheelchair access")
            user_data['language_pref'] = st.selectbox("Preferred Language", ["English", "Hindi", "Local Language"])

        return user_data

    def generate_trip_plan_with_data(self, user_data: dict, travel_data: dict) -> str:
        """Generate trip plan using AI with real-time data."""
        if not self.groq_client: 
            return "Error: AI service is not available."
        
        try:
            duration = (user_data['return_date'] - user_data['departure_date']).days + 1
        except:
            duration = 7

        # Format data for prompt
        destination_overview = ""
        if travel_data['destination_info']:
            destination_overview = f"""
DESTINATION OVERVIEW:
{travel_data['destination_info'].get('extract', 'Beautiful destination with rich culture and attractions')[:400]}...
Location: {travel_data['destination_info'].get('title', 'Unknown')}
"""

        accommodation_info = ""
        if travel_data['accommodation_data'].get('info'):
            acc_data = travel_data['accommodation_data']
            accommodation_info = f"""
CURRENT ACCOMMODATION INFORMATION:
Price Range: {acc_data['price_range']}
Market Details: {acc_data['info'].get('abstract', '')} {acc_data['info'].get('answer', '')}
"""

        transportation_info = ""
        if travel_data['transportation_data'].get('info'):
            trans_data = travel_data['transportation_data']
            transportation_info = f"""
CURRENT TRANSPORTATION INFORMATION:
Price Range: {trans_data['price_range']}
Route Details: {trans_data['info'].get('abstract', '')} {trans_data['info'].get('answer', '')}
"""

        prompt = f"""
        Create a comprehensive, personalized trip itinerary using current travel information and real-time data.

        {destination_overview}
        {accommodation_info}
        {transportation_info}

        **TRAVELER DETAILS:**
        - Name: {user_data.get('name', 'N/A')}
        - Group: {user_data.get('num_travelers')} travelers ({user_data.get('trip_type')} trip)
        - Route: {user_data.get('departure_city')} to {user_data.get('destination')} for {duration} days
        - Dates: {user_data.get('departure_date')} to {user_data.get('return_date')}
        - Budget: Rs. {user_data.get('total_budget', 0):,} ({user_data.get('budget_category', 'Mid-Range')})
        - Primary Interests: {', '.join(user_data.get('interests', ['General']))}
        - Travel Pace: {user_data.get('travel_pace', 'Moderate')}
        - Preferred Transport: {', '.join(user_data.get('transport_mode', ['Flight']))}
        - Dietary Preference: {user_data.get('dietary_pref', 'No Preference')}

        **CREATE A DETAILED ITINERARY WITH:**

        # {user_data.get('destination')} Trip Plan

        ## 🌟 Destination Overview
        Provide an engaging overview of {user_data.get('destination')} including what makes this destination special for {user_data.get('trip_type', 'travelers').lower()} trips, weather conditions, and cultural highlights perfect for travelers interested in {', '.join(user_data.get('interests', ['sightseeing'])[:3]).lower()}.

        ## 📅 Day-by-Day Itinerary
        Create a detailed {duration}-day itinerary with:
        
        **Day 1 - {user_data.get('departure_date')} - Arrival Day**
        - Arrival and check-in activities
        - Light exploration and orientation  
        - Welcome dinner recommendations
        - Estimated daily cost for group: Rs. [amount]

        **Days 2-{duration-1} - Main Exploration**
        For each day include:
        - Morning, afternoon, and evening activities
        - Mix of {', '.join(user_data.get('interests', ['sightseeing']))} experiences
        - Specific timing and travel between locations
        - Meal recommendations for {user_data.get('dietary_pref', 'mixed')} preferences
        - Rest periods for {user_data.get('travel_pace', 'moderate').lower()}-paced travel
        - Daily cost estimates

        **Day {duration} - {user_data.get('return_date')} - Departure Day**
        - Final activities and check-out
        - Last-minute shopping or relaxation
        - Departure arrangements

        ## 🏨 Accommodation Recommendations
        Based on current market data:
        
        **Budget Options (Rs. 1,500-3,000/night):**
        - 2-3 specific budget hotels with amenities and location advantages
        
        **Mid-range Options (Rs. 3,000-6,000/night):**
        - 2-3 mid-range hotels perfect for {user_data.get('trip_type', 'travelers').lower()} groups
        
        **Premium Options (Rs. 6,000+/night):**
        - 2-3 luxury options with full amenities

        ## ✈️ Transportation Guide
        **Main Travel:**
        - {user_data.get('departure_city')} to {user_data.get('destination')} best options
        - Current pricing and booking strategies
        
        **Local Transportation:**
        - Most efficient ways to reach attractions
        - Cost-effective daily transport options

        ## 💰 Enhanced Budget Breakdown
        Create a table with Category, Allocated Budget, Estimated Cost, and Recommendations columns.

        ## 🍽️ Food & Dining Guide
        Curated for {user_data.get('dietary_pref', 'all')} preferences with must-try local specialties and restaurant recommendations across budget ranges.

        ## 🎯 Activities & Experiences
        Tailored to interests in {', '.join(user_data.get('interests', ['adventure']))} with top attractions, unique experiences, and {user_data.get('travel_pace', 'balanced')} activity scheduling.

        ## 📱 Practical Information
        Include packing essentials, local tips, cultural customs, safety guidelines, and emergency contacts.

        **IMPORTANT:** Use ONLY 'Rs.' for currency (never rupee symbol). Make all recommendations specific and actionable.
        """

        try:
            response = self.groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert travel planner creating detailed, personalized trip plans. Provide specific, actionable recommendations with current pricing using 'Rs.' for currency. Focus on creating memorable experiences matching traveler interests and budget."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
                max_tokens=8000,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"An error occurred while generating the trip plan: {str(e)}"

    def run(self):
        """Main method to run the application."""
        user_data = self.collect_user_inputs()

        if st.button("🚀 Generate My Personalized Trip Plan", type="primary", use_container_width=True):
            required = ['name', 'email', 'destination', 'departure_city', 'mobile', 'total_budget']
            missing = [field.replace('_', ' ').title() for field in required if not user_data.get(field)]
            
            if missing:
                st.error(f"Please fill in required fields: {', '.join(missing)}")
                return
            
            if user_data['return_date'] < user_data['departure_date']:
                st.error("Return date must be after departure date.")
                return

            if not user_data.get('transport_mode'):
                st.error("Please select your preferred transportation.")
                return

            # Validate email format
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, user_data['email']):
                st.error("Please enter a valid email address.")
                return

            # Gather travel data
            with st.spinner("🔍 Gathering current travel information and pricing..."):
                travel_data = self.gather_travel_data(user_data)

            # Generate trip plan
            try:
                duration = (user_data['return_date'] - user_data['departure_date']).days + 1
            except:
                duration = 7
                
            with st.spinner(f"🤖 Creating your personalized {duration}-day {user_data['destination']} itinerary..."):
                trip_plan = self.generate_trip_plan_with_data(user_data, travel_data)

            if trip_plan and not trip_plan.startswith("An error"):
                st.markdown('<div class="trip-plan"><h3>🎯 Your Personalized Trip Plan</h3></div>', unsafe_allow_html=True)
                st.markdown(trip_plan)
                
                with st.spinner("📧 Creating PDF and sending your trip plan..."):
                    if self.send_email(user_data['email'], user_data['name'], trip_plan, user_data):
                        st.success(f"✅ Trip plan sent successfully to {user_data['email']}!")
                        st.balloons()
                        
                        # Enhanced success message
                        st.markdown(f"""
                        <div class="success-message">
                        <h4>🎉 Your {duration}-day {user_data.get('destination')} adventure plan includes:</h4>
                        <ul>
                            <li>📍 <strong>Real-time destination insights</strong> with current travel information</li>
                            <li>📅 <strong>Complete day-by-day itinerary</strong> for {user_data.get('travel_pace', 'moderate').lower()}-paced travel</li>
                            <li>🏨 <strong>Accommodation recommendations</strong> for your {user_data.get('budget_category', 'budget')} range</li>
                            <li>✈️ <strong>Transportation guide</strong> with {', '.join(user_data.get('transport_mode', ['multiple']))} options</li>
                            <li>💰 <strong>Detailed budget breakdown</strong> totaling Rs. {user_data.get('total_budget', 0):,}</li>
                            <li>🍽️ <strong>Food recommendations</strong> for {user_data.get('dietary_pref', 'your preferences').lower()} preferences</li>
                            <li>🎯 <strong>Activities tailored</strong> to: {', '.join(user_data.get('interests', ['General']))}</li>
                            <li>🎒 <strong>Comprehensive packing tips</strong> with seasonal and interest-specific recommendations</li>
                            <li>🌍 <strong>Local tips and cultural guidelines</strong> for authentic experiences</li>
                            <li>📱 <strong>Emergency contacts</strong> with local and national helplines</li>
                        </ul>
                        <p><strong>Perfect for your {user_data.get('trip_type', 'adventure').lower()} trip with {user_data.get('num_travelers')} travelers! 🌟</strong></p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.warning("Trip plan created successfully, but email delivery failed. Please check your connection and try again.")
            else:
                st.error(f"Failed to generate trip plan: {trip_plan}")

        # Clean footer
        st.markdown("---")
        st.markdown("### ✨ Powered by AI + Real-time Travel Data")
        st.markdown("Get personalized trip plans with current pricing, real-time information, and professional PDF reports delivered to your inbox!")


if __name__ == "__main__":
    app = AITripPlanner()
    app.run()

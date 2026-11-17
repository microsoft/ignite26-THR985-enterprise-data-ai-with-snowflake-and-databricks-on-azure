"""Reference data for the Contoso Retail synthetic dataset. Every name here is fictitious."""

REGIONS = ["West", "East", "Central", "South"]
REGION_CODE = {"West": "W", "East": "E", "Central": "C", "South": "S"}
REGION_AREA_CODE = {"West": "206", "East": "617", "Central": "312", "South": "404"}
REGION_DEMAND = {"West": 1.00, "East": 1.05, "Central": 0.95, "South": 1.00}

CITIES = {
    "West": [("Seattle", "WA"), ("Tacoma", "WA"), ("Spokane", "WA"), ("Portland", "OR"), ("Eugene", "OR"), ("Boise", "ID"),
             ("Sacramento", "CA"), ("San Jose", "CA"), ("Fresno", "CA"), ("Reno", "NV"), ("Phoenix", "AZ"), ("Tucson", "AZ")],
    "East": [("Boston", "MA"), ("Worcester", "MA"), ("Providence", "RI"), ("Hartford", "CT"), ("New Haven", "CT"), ("Albany", "NY"),
             ("Buffalo", "NY"), ("Rochester", "NY"), ("Newark", "NJ"), ("Philadelphia", "PA"), ("Pittsburgh", "PA"), ("Baltimore", "MD")],
    "Central": [("Chicago", "IL"), ("Naperville", "IL"), ("Milwaukee", "WI"), ("Madison", "WI"), ("Minneapolis", "MN"), ("Des Moines", "IA"),
                ("Omaha", "NE"), ("Kansas City", "MO"), ("St. Louis", "MO"), ("Indianapolis", "IN"), ("Columbus", "OH"), ("Detroit", "MI")],
    "South": [("Atlanta", "GA"), ("Savannah", "GA"), ("Charlotte", "NC"), ("Raleigh", "NC"), ("Nashville", "TN"), ("Memphis", "TN"),
              ("Birmingham", "AL"), ("Jacksonville", "FL"), ("Orlando", "FL"), ("Tampa", "FL"), ("Dallas", "TX"), ("Houston", "TX")],
}

FORMAT_CYCLE = ["Superstore", "Neighborhood", "Neighborhood", "Express"]
FORMAT_SIZE = {"Superstore": 1.8, "Neighborhood": 1.0, "Express": 0.55}
FORMAT_SQFT = {"Superstore": 65000, "Neighborhood": 38000, "Express": 12000}
# Days of forward cover each format keeps on hand (superstores have deep backrooms).
FORMAT_TARGET_DOS = {"Superstore": 10, "Neighborhood": 5, "Express": 3}

DCS = [  # dc_id, dc_name, city, state, region
    ("DC-W", "Contoso DC West", "Reno", "NV", "West"),
    ("DC-E", "Contoso DC East", "Harrisburg", "PA", "East"),
    ("DC-C", "Contoso DC Central", "Indianapolis", "IN", "Central"),
    ("DC-S", "Contoso DC South", "Atlanta", "GA", "South"),
]

SUPPLIERS = [  # supplier_id, supplier_name, category, hq_city, hq_state, lead_time_days
    ("SUP01", "Northwind Traders", "Beverages", "Tacoma", "WA", 6),
    ("SUP02", "Fabrikam Foods", "Snacks", "Chicago", "IL", 6),
    ("SUP03", "Proseware Dairy Co-op", "Dairy", "Madison", "WI", 3),
    ("SUP04", "Litware Bakehouse", "Bakery", "Columbus", "OH", 2),
    ("SUP05", "Tailspin Farms", "Produce", "Fresno", "CA", 3),
    ("SUP06", "Alpine Frozen Foods", "Frozen", "Minneapolis", "MN", 7),
    ("SUP07", "Wide World Importers", "Household", "Newark", "NJ", 9),
    ("SUP08", "Adventure Works Care", "Personal Care", "Raleigh", "NC", 8),
]

CASE_PACK = {"Beverages": 12, "Snacks": 12, "Dairy": 6, "Bakery": 6, "Produce": 10, "Frozen": 6, "Household": 12, "Personal Care": 6}

# category, code, subcategory, velocity (units/day in a neighborhood store), (price_lo, price_hi), brands, items
CATALOG = [
    ("Beverages", "BEV", "Sparkling Water", 8.0, (5.49, 6.99), ["Northwind Sparkle", "Contoso Select"],
     ["Lime 12x12oz", "Lemon 12x12oz", "Grapefruit 12x12oz", "Black Cherry 12x12oz", "Mango 12x12oz", "Mixed Berry 12x12oz", "Original 12x12oz", "Peach 12x12oz"]),
    ("Beverages", "BEV", "Soda", 7.0, (5.99, 7.49), ["Fizzwell", "Contoso Select"],
     ["Cola 12x12oz", "Diet Cola 12x12oz", "Lemon-Lime 12x12oz", "Root Beer 12x12oz", "Ginger Ale 12x12oz", "Orange 12x12oz", "Cola 2L"]),
    ("Beverages", "BEV", "Energy Drinks", 9.0, (2.79, 3.49), ["Volt Energy"],
     ["Original 16oz", "Sugar-Free 16oz", "Tropical 16oz", "Berry Blast 16oz", "Original 4x16oz", "Zero Ultra 4x16oz"]),
    ("Beverages", "BEV", "Juice", 4.0, (3.99, 5.49), ["Orchard Gold", "Contoso Select"],
     ["Orange 52oz", "Apple 52oz", "Cranberry 64oz", "Grape 64oz", "Tropical 52oz"]),
    ("Beverages", "BEV", "Bottled Water", 8.0, (4.49, 6.99), ["Summit Springs", "Contoso Select"],
     ["Spring Water 24x16.9oz", "Purified 24x16.9oz", "Alkaline 1L", "Sparkling Mineral 1L"]),
    ("Snacks", "SNK", "Chips", 5.0, (3.99, 5.49), ["Fabrikam Crunch", "Contoso Select", "Golden Grove"],
     ["Sea Salt 8oz", "BBQ 8oz", "Sour Cream & Onion 8oz", "Jalapeno 8oz", "Salt & Vinegar 8oz", "Cheddar 8oz", "Tortilla Rounds 11oz", "Kettle Original 8oz"]),
    ("Snacks", "SNK", "Crackers", 3.0, (3.49, 4.99), ["Golden Grove", "Contoso Select"],
     ["Wheat 9oz", "Multigrain 9oz", "Cheese 7oz", "Rice 3.5oz", "Sea Salt 9oz", "Everything 9oz"]),
    ("Snacks", "SNK", "Nuts & Trail Mix", 2.2, (6.99, 11.99), ["Trailhead", "Contoso Select"],
     ["Almonds 16oz", "Cashews 10oz", "Mixed Nuts 15oz", "Trail Mix 26oz", "Peanuts 16oz", "Pistachios 12oz"]),
    ("Snacks", "SNK", "Cookies", 3.0, (3.99, 5.99), ["Fabrikam Bakery", "Contoso Select"],
     ["Chocolate Chip 13oz", "Oatmeal Raisin 13oz", "Double Chocolate 13oz", "Shortbread 10oz", "Sandwich Cremes 14oz", "Snickerdoodle 13oz"]),
    ("Snacks", "SNK", "Candy", 4.0, (1.49, 4.99), ["Sweetwater", "Contoso Select"],
     ["Milk Chocolate Bar 3oz", "Gummy Bears 7oz", "Peanut Butter Cups 6pk", "Sour Strips 5oz"]),
    ("Dairy", "DRY", "Milk", 13.0, (3.49, 5.99), ["Meadowbrook", "Contoso Select"],
     ["Whole Milk 1gal", "2% Milk 1gal", "Skim Milk 1gal", "Oat Milk 64oz", "Almond Milk 64oz", "Lactose-Free 2% 64oz", "Chocolate Milk 1qt"]),
    ("Dairy", "DRY", "Yogurt", 6.0, (1.29, 6.49), ["Meadowbrook", "Proseware Farms"],
     ["Greek Plain 32oz", "Greek Vanilla 32oz", "Strawberry 5.3oz", "Blueberry 5.3oz", "Peach 5.3oz", "Kids Variety 8pk", "Plain 32oz"]),
    ("Dairy", "DRY", "Cheese", 4.0, (3.99, 8.99), ["Proseware Farms", "Contoso Select"],
     ["Sharp Cheddar Block 8oz", "Shredded Mozzarella 16oz", "Swiss Slices 8oz", "Grated Parmesan 8oz", "Pepper Jack Block 8oz", "String Cheese 12pk", "Brie 8oz"]),
    ("Dairy", "DRY", "Butter & Cream", 3.0, (3.49, 6.49), ["Meadowbrook"],
     ["Salted Butter 16oz", "Unsalted Butter 16oz", "Heavy Cream 16oz", "Half & Half 32oz"]),
    ("Bakery", "BKY", "Bread", 8.0, (2.99, 5.99), ["Litware Hearth", "Contoso Select"],
     ["White Sandwich Loaf", "Whole Wheat Loaf", "Sourdough Loaf", "Multigrain Loaf", "Rye Loaf", "Brioche Loaf", "Hamburger Buns 8pk", "Hot Dog Buns 8pk"]),
    ("Bakery", "BKY", "Pastries", 4.0, (3.99, 6.99), ["Litware Hearth"],
     ["Butter Croissants 4pk", "Blueberry Muffins 4pk", "Cinnamon Rolls 4pk", "Danish Assortment 6pk", "Plain Bagels 6pk", "Glazed Donuts 6pk"]),
    ("Bakery", "BKY", "Tortillas & Wraps", 3.0, (2.99, 4.49), ["Litware Hearth", "Contoso Select"],
     ["Flour Tortillas 10ct", "Corn Tortillas 30ct", "Spinach Wraps 6ct", "Whole Wheat Wraps 8ct", "Garlic Naan 4ct", "Pita Pockets 6ct"]),
    ("Produce", "PRD", "Fruit", 11.0, (0.69, 5.99), ["Tailspin Farms"],
     ["Bananas per lb", "Gala Apples 3lb", "Navel Oranges 4lb", "Strawberries 16oz", "Blueberries 11oz", "Red Grapes per lb", "Hass Avocados 4ct", "Lemons 2lb", "Pineapple each", "Mango each"]),
    ("Produce", "PRD", "Vegetables", 8.0, (1.29, 4.99), ["Tailspin Farms"],
     ["Baby Carrots 16oz", "Broccoli Crowns per lb", "Romaine Hearts 3ct", "Russet Potatoes 5lb", "Yellow Onions 3lb", "Vine Tomatoes per lb", "Cucumber each", "Bell Peppers 3pk", "Sweet Corn 4ct", "White Mushrooms 8oz"]),
    ("Produce", "PRD", "Salad Kits", 3.0, (3.99, 4.99), ["Tailspin Farms"],
     ["Caesar Salad Kit", "Southwest Chopped Kit", "Asian Sesame Kit", "Greek Salad Kit", "Spring Mix 5oz"]),
    ("Frozen", "FRZ", "Frozen Meals", 4.0, (3.49, 8.99), ["Alpine Kitchen", "Contoso Select"],
     ["Chicken Alfredo", "Beef Lasagna", "Veggie Stir Fry", "Margherita Pizza", "Pepperoni Pizza", "Bean & Cheese Burritos 8pk", "Chicken Tikka Masala", "Mac & Cheese"]),
    ("Frozen", "FRZ", "Ice Cream", 3.0, (4.49, 6.99), ["Polar Scoop", "Contoso Select"],
     ["Vanilla Bean 1.5qt", "Chocolate Fudge 1.5qt", "Cookie Dough 1.5qt", "Mint Chip 1.5qt", "Strawberry 1.5qt", "Salted Caramel 1.5qt"]),
    ("Frozen", "FRZ", "Frozen Vegetables", 2.5, (1.79, 3.49), ["Alpine Kitchen", "Contoso Select"],
     ["Sweet Peas 12oz", "Mixed Vegetables 12oz", "Broccoli Florets 12oz", "Sweet Corn 12oz", "Green Beans 12oz", "Stir-Fry Blend 16oz"]),
    ("Household", "HSH", "Cleaning", 2.0, (2.99, 8.99), ["BrightHome", "Contoso Select"],
     ["All-Purpose Spray 32oz", "Glass Cleaner 26oz", "Disinfecting Wipes 75ct", "Dish Soap 24oz", "Bathroom Cleaner 32oz", "Floor Cleaner 48oz", "Sponges 6pk", "Bleach 81oz", "Dishwasher Pods 42ct"]),
    ("Household", "HSH", "Paper Goods", 3.0, (3.99, 19.99), ["BrightHome", "Contoso Select"],
     ["Paper Towels 6 Rolls", "Bath Tissue 12 Rolls", "Facial Tissue 4pk", "Napkins 200ct", "Paper Plates 50ct", "Trash Bags 40ct", "Aluminum Foil 75sqft", "Plastic Wrap 200sqft"]),
    ("Household", "HSH", "Laundry", 1.8, (6.99, 15.99), ["Wide World Clean", "Contoso Select"],
     ["Liquid Detergent 92oz", "Detergent Pods 42ct", "Fabric Softener 64oz", "Dryer Sheets 120ct", "Stain Remover 22oz", "Free & Clear Detergent 92oz", "Oxi Booster 3lb", "Delicates Wash 16oz"]),
    ("Personal Care", "PCR", "Oral Care", 1.5, (2.99, 14.99), ["Adventure Works Care", "Contoso Select"],
     ["Whitening Toothpaste 4.8oz", "Sensitive Toothpaste 4oz", "Mint Mouthwash 1L", "Soft Toothbrush 2pk", "Mint Floss 50yd", "Kids Toothpaste 4.2oz", "Electric Brush Heads 3pk"]),
    ("Personal Care", "PCR", "Hair Care", 1.5, (4.99, 9.99), ["PureLeaf Botanics", "Contoso Select"],
     ["Moisture Shampoo 12oz", "Moisture Conditioner 12oz", "2-in-1 Shampoo 12oz", "Dry Shampoo 4oz", "Styling Gel 8oz", "Anti-Dandruff Shampoo 12oz", "Argan Hair Oil 3oz"]),
    ("Personal Care", "PCR", "Skin Care", 1.5, (2.99, 12.99), ["PureLeaf Botanics", "Adventure Works Care"],
     ["Body Wash 18oz", "Hand Soap 12oz", "Face Moisturizer SPF30 3oz", "Body Lotion 16oz", "Lip Balm 3pk", "Sunscreen SPF50 6oz"]),
    ("Personal Care", "PCR", "Vitamins", 0.8, (8.99, 19.99), ["Adventure Works Care", "Contoso Select"],
     ["Daily Multivitamin 100ct", "Vitamin D3 2000IU 90ct", "Vitamin C 1000mg 60ct", "Omega-3 Fish Oil 90ct", "Daily Probiotic 30ct"]),
]

PRICE_OVERRIDES = {"4x16oz": (9.49, 10.99), "2L": (2.29, 2.79), " 1L": (1.79, 2.49)}

BEVERAGE_SUBCATS = ["Sparkling Water", "Soda", "Energy Drinks", "Juice", "Bottled Water"]
SNACK_SUBCATS = ["Chips", "Crackers", "Nuts & Trail Mix", "Cookies"]

_BEV_SUMMER = {5: 1.05, 6: 1.20, 7: 1.30, 8: 1.25, 9: 1.05, 10: 0.93, 11: 0.90}
# Mid-month seasonal multipliers by subcategory (missing months = 1.0).
SEASON = {
    "Sparkling Water": _BEV_SUMMER, "Soda": _BEV_SUMMER,
    "Energy Drinks": {5: 1.00, 6: 1.08, 7: 1.12, 8: 1.10, 9: 1.02, 10: 0.97, 11: 0.95},
    "Bottled Water": {5: 1.10, 6: 1.30, 7: 1.40, 8: 1.35, 9: 1.10, 10: 0.90, 11: 0.85},
    "Juice": {10: 1.04, 11: 1.06},
    "Ice Cream": {5: 1.20, 6: 1.45, 7: 1.60, 8: 1.50, 9: 1.10, 10: 0.82, 11: 0.72},
    "Fruit": {6: 1.08, 7: 1.10, 8: 1.08},
    "Vegetables": {6: 1.05, 7: 1.08, 8: 1.06},
    "Salad Kits": {6: 1.12, 7: 1.15, 8: 1.12, 10: 0.95, 11: 0.90},
    "Frozen Meals": {6: 0.95, 7: 0.93, 8: 0.95, 10: 1.05, 11: 1.08},
}

DOW = [0.86, 0.86, 0.90, 0.95, 1.12, 1.30, 1.01]  # Monday..Sunday

PROMO_LIFT_K = {"TPR": 1.6, "Digital Coupon": 1.0, "Bundle": 1.3}
PROMO_NAMES = {
    "TPR": ["{sub} Savings", "Weekly Deal: {sub}", "Fresh Price: {sub}", "Stock-Up Sale: {sub}"],
    "Digital Coupon": ["App Exclusive: {sub}", "Loyalty Coupon: {sub}"],
    "Bundle": ["Mix & Match: {sub}", "Bundle & Save: {sub}"],
}

FIRST_NAMES = ["Ava", "Liam", "Sofia", "Noah", "Mia", "Ethan", "Isabella", "Lucas", "Amara", "Mateo", "Zoe", "Arjun", "Chloe",
               "Kenji", "Priya", "Diego", "Hannah", "Omar", "Leila", "Samuel", "Grace", "Wei", "Nora", "Elijah", "Fatima", "Jonah",
               "Maya", "Andre", "Lucia", "Tariq", "Elena", "Kofi", "Aisha", "Daniel", "Yuki", "Gabriel", "Ines", "Marcus", "Sana",
               "Theo", "Camila", "Ravi", "Olivia", "Hugo", "Naomi", "Felix", "Zara", "Malik", "Ingrid", "Rafael"]
LAST_NAMES = ["Anderson", "Nguyen", "Patel", "Garcia", "Johnson", "Kim", "Martinez", "Okafor", "Silva", "Chen", "Rossi",
              "Haddad", "Kowalski", "Brown", "Tanaka", "Lopez", "Schmidt", "Ali", "Murphy", "Singh", "Dubois", "Mensah",
              "Ivanova", "Walker", "Costa", "Fischer", "Ramirez", "Park", "Novak", "Ahmed", "Larsen", "Moreau", "Yilmaz",
              "Hughes", "Castillo", "Bauer", "Sato", "Reyes", "Osei", "Bennett"]

ROUTINE_NOTES = [  # topic, author_role, store_level, template
    ("Planogram", "Store Manager", True,
     "Completed the planogram reset for {subcat} in aisle {aisle}. Moved {k} items to eye level and delisted two slow movers."),
    ("Weather", "Regional Manager - {region}", False,
     "{weather} expected this weekend across {region}; raised {category} orders by {pct}% for the affected stores."),
    ("Local event", "Store Manager", True,
     "{event} nearby on Saturday, expecting heavier foot traffic. Added an extra {category} display near the entrance."),
    ("Staffing", "Store Manager", True,
     "Short {n} associates on the {shift} shift; restocking of {category} finished late but shelves were full by opening."),
    ("Competitor", "Category Manager - {category}", False,
     "A nearby competitor is running {deal} on {subcat}; our shelf price is about {pct}% higher this week."),
    ("Customer feedback", "Store Manager", True,
     "Several customers asked for more {subcat} options, especially {item}. Logged for the next category review."),
    ("Supplier delivery", "Supply Planner - {region}", False,
     "{supplier} delivery to {dc} arrived {hours} hours late; no store impact expected."),
    ("Shrink", "Store Manager", True,
     "Shrink on {subcat} was higher than usual this week; reviewing receiving and rotation practices with the team."),
]
WEATHER = ["A heat wave", "Heavy rain", "Thunderstorms", "Clear, warm weather", "An early cold snap"]
EVENTS = ["A high school football game", "The farmers market", "A street festival", "College move-in weekend", "A city marathon", "The county fair"]
DEALS = ["buy-one-get-one", "20% off", "2-for-$5", "double loyalty points"]
SHIFTS = ["morning", "evening", "overnight"]

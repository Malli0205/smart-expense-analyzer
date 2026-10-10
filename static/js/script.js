document.addEventListener("DOMContentLoaded", function () {

    const categorySelect = document.getElementById("category");
    const subCategorySelect = document.getElementById("sub_category");

    if (!categorySelect || !subCategorySelect) {
        return;
    }

    const subCategories = {

        "Food": [
            "Local Food",
            "Home Made Food",
            "Restaurant",
            "Fast Food",
            "Groceries",
            "Fruits & Vegetables",
            "Snacks",
            "Beverages"
        ],

        "Travel": [
            "Bus",
            "Train",
            "Auto",
            "Cab",
            "Fuel",
            "Flight",
            "Parking",
            "Vehicle Maintenance"
        ],

        "Shopping": [
            "Clothes",
            "Shoes",
            "Electronics",
            "Accessories",
            "Cosmetics",
            "Household Items",
            "Online Shopping"
        ],

        "Education": [
            "College Fees",
            "Books",
            "Courses",
            "Certifications",
            "Stationery",
            "Exam Fees"
        ],

        "Bills & Utilities": [
            "Electricity",
            "Water",
            "Internet",
            "Mobile Recharge",
            "Gas",
            "Other"
        ],

        "Health": [
            "Medicines",
            "Doctor Consultation",
            "Medical Tests",
            "Hospital",
            "Other"
        ],

        "Entertainment": [
            "Movies",
            "OTT Subscription",
            "Games",
            "Events",
            "Music",
            "Other"
        ],

        "Home": [
            "Rent",
            "Furniture",
            "Repairs",
            "Cleaning",
            "Kitchen Items",
            "Other"
        ]
    };


    categorySelect.addEventListener("change", function () {

        const selectedCategory = categorySelect.value;

        subCategorySelect.innerHTML = "";

        const defaultOption = document.createElement("option");

        defaultOption.value = "";
        defaultOption.textContent = "Select Sub Category";

        subCategorySelect.appendChild(defaultOption);

        const categories = subCategories[selectedCategory];

        if (categories) {

            categories.forEach(function (subcategory) {

                const option = document.createElement("option");

                option.value = subcategory;
                option.textContent = subcategory;

                subCategorySelect.appendChild(option);

            });

        }

    });

});